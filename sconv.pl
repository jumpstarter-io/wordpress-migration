#!/usr/bin/env perl -w

###
# This is free and unencumbered software released into the public domain.
#
# Anyone is free to copy, modify, publish, use, compile, sell, or
# distribute this software, either in source code form or as a compiled
# binary, for any purpose, commercial or non-commercial, and by any
# means.
#
# In jurisdictions that recognize copyright laws, the author or authors
# of this software dedicate any and all copyright interest in the
# software to the public domain. We make this dedication for the benefit
# of the public at large and to the detriment of our heirs and
# successors. We intend this dedication to be an overt act of
# relinquishment in perpetuity of all present and future rights to this
# software under copyright law.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
# EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
# MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.
# IN NO EVENT SHALL THE AUTHORS BE LIABLE FOR ANY CLAIM, DAMAGES OR
# OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE,
# ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR
# OTHER DEALINGS IN THE SOFTWARE.
#
# For more information, please refer to <http://unlicense.org/>
###

###
# Usage:
#    cat sqldump.sql | ./sconv.pl | sqlite3 db.sqlite
#
###

use strict;
use warnings;

sub clean_tbl_non_key_row {
    my ($row) = @_;
    if ($row =~ /AUTO_INCREMENT/i) {
        $row =~ s/AUTO_INCREMENT/PRIMARY KEY AUTOINCREMENT/i;
    }
    $row =~ s/UNIQUE KEY `.*` /UNIQUE /i;
    $row =~ s/CHARACTER SET [^ ]+ //i;
    $row =~ s/DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP//i;
    $row =~ s/COLLATE [^ ]+//i;
    $row =~ s/ENUM[^)]+\)/text /i;
    $row =~ s/SET\([^)]\)/text /i;
    $row =~ s/UNSIGNED//i;
    $row =~ s/`\s+[^ ]*int[^ ]*/` integer/i;
    return $row;
}

sub create_index {
    my ($table_name, $index_name, $index_key, $unique) = @_;
    my $index = "CREATE ";
    if ($unique) {
        $index .= "UNIQUE ";
    }
    $index .= "INDEX \"";
    $index .= $table_name . "_" . $index_name;
    $index .= "\" ON \"";
    $index .= $table_name;
    $index .= "\" (" . $index_key . ");";
    return $index;
}

my @tables = ();
my @inserts = ();

my $in_insert = 0;
my $in_table = 0;
my $in_alter_table = 0;
my $in_trigger = 0;
my $in_view = 0;

my $curr_table_name = "";
my @curr_table_lines = ();
my @indexes = ();
my @triggers = ();
my @views = ();

my @curr_insert = ();
my @curr_trigger = ();
my @curr_view = ();

foreach my $line (<STDIN>) {

    $line =~ s/,(\n)?$//;

    # CREATE VIEW looks like a TABLE in comments.
    if ($line =~ /^\/\*.*CREATE.*TABLE/ || $in_view) {
        $in_view = 1;
        if ($line =~ /^(\).*ENGINE.*\*\/;)/) {
            $in_view = 0;
            push @curr_view, ");";
            push @views, join("\n", @curr_view);
            @curr_view = ();
            next;
        }
        push @curr_view, $line;
    }

    # skip all other comments
    if ($line =~ /^#/ || $line =~ /\/\*/) {
        next;
    }

    if ($line =~ /^CREATE\s+TABLE\s+`([^`]+)`\s+\(/i || $in_table) {
        if (!$in_table) {
            $curr_table_name = $1;
            $in_table = 1;
            next;
        }
        if ($line =~ /ENGINE/) {
            # Found the end of the table spec.
            $in_table = 0;
            # Need to copy the arrays since we can only push array refs into the hash.
            my @table_lines = @curr_table_lines;
            push (@tables, {
                name => $curr_table_name,
                rows => \@table_lines,
            });
            $curr_table_name = "";
            @curr_table_lines = ();
            next;
        }

        $line =~ s/\n$//;

        if ($line =~ /FULLTEXT\s+KEY/) {
            $line =~ s/.+KEY/  KEY/g;
        }

        if ($line =~ /(PRIMARY )?KEY/) {
            $line =~ s/\([0-9]+\)//g;
        }

        if ($line =~ /PRIMARY KEY/) {
            next;
        }

        if ($line !~ /^(\s+KEY|\);)/) {
            $line = clean_tbl_non_key_row($line);
        }

        if ($line =~ /\s+KEY\s+`([^`]+)`\s+\(([^)]+)\)/) {
            my $index_name = $1;
            my $index_key = $2;
            push @indexes, create_index($curr_table_name, $index_name, $index_key, 0);
        } else {
            push @curr_table_lines, $line;
        }
    }

    if ($line =~ /^INSERT/ || $in_insert) {
        $in_insert = 1;
        $line =~ s/\n$//;
        $line =~ s/^\s+//;
        # skip empty inserts.
        if ($line =~ /VALUES;/) {
            $in_insert = 0;
            @curr_insert = ();
            next;
        }
        if ($line =~ /\);$/) {
            push @curr_insert, $line;
            my $ins = join(" ", @curr_insert);
            $ins =~ s/\\\047/\047\047/g;
            $ins =~ s/\\\047\047/\\\047/g;
            $ins =~ s/\\n/\n/g;
            $ins =~ s/\\r/\r/g;
            $ins =~ s/\\"/\"/g;
            $ins =~ s/\\\\/\\/g;
            $ins =~ s/\\\032/\032/g;
            push @inserts, $ins;
            @curr_insert = ();
            $in_insert = 0;
            next;
        }
        push @curr_insert, $line;
    }

    if ($line =~ /ALTER TABLE `([^`]+)`/ || $in_alter_table) {
        if (!$in_alter_table) {
            $curr_table_name = $1;
        }
        $in_alter_table = 1;
        if ($line =~ /(\);|;)$/) {
            $in_alter_table = 0;
        }
        $line =~ s/\([0-9]+\)//g;
        if ($line =~ /ADD\s+PRIMARY\s+KEY\s+\(`([^`]+)`\)/i) {
            my $col_name = $1;
            #print "should add primary key " . $col_name . " to " . $curr_table_name . "\n";
            for my $table (@tables) {
                if ($table->{name} eq $curr_table_name) {
                    my @rows = @{$table->{rows}};
                    for my $i (0 .. $#rows) {
                        if (index($rows[$i], $col_name) != -1) {
                            if ($rows[$i] !~ /PRIMARY KEY/) {
                                $rows[$i] = $rows[$i] . " PRIMARY KEY";
                            }
                            last;
                        }
                    }
                    $table->{rows} = \@rows;
                }
            }
            next;
        }

        if ($line =~ /ADD\s+UNIQUE\s+KEY\s+`([^`]+)`s+\(`([^`]+)`\)/i) {
            my ($index_name, $index_key) = ($1, $2);
            push @indexes, create_index($curr_table_name, $index_name, $index_key, 1);
            next;
        }

        if ($line =~ /ADD\s+KEY\s+`([^`]+)`\s+\(([^)]+)\)/) {
            my ($index_name, $index_key) = ($1, $2);
            push @indexes, create_index($curr_table_name, $index_name, $index_key, 0);
            next;
        }

        if ($line =~ /MODIFY\s+`([^`]+)`([^,;]+)/) {
            my ($col_name, $col_def) = ($1, $2);
            $col_def =~ s/\([0-9]+\)//i;
            # remember to watch out for primary key definition.
            for my $table (@tables) {
                if ($table->{name} eq $curr_table_name) {
                    #print "found table\n";
                    my @rows = @{$table->{rows}};
                    for my $i (0 .. $#rows) {
                        if (index($rows[$i], $col_name) != -1) {
                            $rows[$i] = clean_tbl_non_key_row("`" . $col_name . "` " . $col_def);
                            last;
                        }
                    }
                    $table->{rows} = \@rows;
                }
            }
        }
    }

    if ($line =~ /^\/\*.*CREATE.*TRIGGER/ || $in_trigger) {
        $in_trigger = 1;
        $line =~ s/^.*TRIGGER/CREATE TRIGGER/;
        if ($line =~ /END \*\/;;/) {
            $line =~ s/\*\///;
            push @curr_trigger, $line;
            push @triggers, join("\n", @curr_trigger);
            @curr_trigger = ();
            $in_trigger = 0;
            next;
        }
        push @curr_trigger, $line;
    }
}

print "PRAGMA synchronous = OFF;\n";
print "PRAGMA journal_mode = MEMORY;\n";
print "BEGIN TRANSACTION;\n";

foreach my $table (@tables) {
    print "CREATE TABLE `$table->{name}` (\n";
    print join(",\n", @{$table->{rows}}) . "\n";
    print ");\n";
}

foreach my $insert (@inserts) {
    print $insert . "\n";
}

foreach my $index (@indexes) {
    print $index . "\n";
}

foreach my $trigger (@triggers) {
    print $trigger, "\n";
}

print "END TRANSACTION;\n"
