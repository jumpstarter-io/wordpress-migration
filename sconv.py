#!/usr/bin/env python2

#####
# This script is written to work with phpmyadmin sql dumps using the following configuration:
#
# output compatibility: NONE
# Syntax to use when inserting data:
#    include column names in every INSERT statement
#      Example: INSERT INTO tbl_name (col_A,col_B,col_C) VALUES (1,2,3)
#
#
# Usage examples:
#   from mysql directly: mysqldump --skip-extended-insert --compact -u<db_user> -p<db_passwd> <db_name> | ./sconv.py -m | sqlite3 db.sqlite
#   from mysql dump    : cat <dump_file> | ./sconv.py -m | sqlite3 db.sqlite
#   from phpmyadmin dump: cat <dump_file> | ./sconv.py -p | ./sconv.py -m | sqlite3 db.sqlite
#
#####

import sys
import os
import re
import shutil
import stat
import argparse


def parse_args():
    parser = argparse.ArgumentParser(description = "The email compiler/checker/syncer")
    parser.add_argument("-p", "--phpmyadmin", help="Convert a file from phpmyadmin format to mysqldump", action="store_true")
    parser.add_argument("-m", "--mysql", help="Convert a file from mysqldump compatible format to sqlite3 format", action="store_true")
    parser.add_argument("-f", "--file", help="File to read from, if not specified the script will assume piped input", nargs=1)
    parser.add_argument("-e", "--echo", help="Should the result be echoed to the terminal?", action="store_true")
    return parser.parse_args()

ARGS = parse_args()

table_order = []
table_defs = {}

ctable_regx = re.compile("^(\s+)?create\s+table\s+(`|\"|')([^`\"']+)(`|\"|')\s+\($", re.I)
etable_regx = re.compile("^(\s+)?\).*;$", re.I)
atable_regx = re.compile("^(\s+)?alter\s+table\s+(`|\"|')([^`\"']+)(`|\"|')$", re.I)
apk_regx = re.compile("^(\s+)?add\s+primary\s+key\s+\((`|\"|')([^`\"']+)(`|\"|')\)(,|;)$", re.I)
add_regx = re.compile("^(\s+)?add\s+(.*)(,|;)$", re.I)
mod_regx = re.compile("^(\s+)?modify([^,]+).*(,|;)$", re.I)
col_regx = re.compile("^(\s+)?(`|\"|')([^`\"']+)(`|\"|')", re.I)
ins_regx = re.compile("^(\s+)?insert\s+into.*$", re.I)
eins_regx = re.compile(".*\)(\s+)?;(\s+)?", re.I)
eval_regx = re.compile(".*values(\s+)?;", re.I)
com_regx = re.compile("^(\s+)?(#|/\*)", re.I)


def phpmyadmin_to_mysql(ifh, ofh=None, echo_results=False):
    if ofh is None:
        ofh = sys.stdout

    output_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")
    output_data_file_path = os.path.join(output_dir, "mysql_data.sql")
    output_dump_file_path = os.path.join(output_dir, "mysql_dump.sql")

    if os.path.exists(output_dir) and os.path.isdir(output_dir):
        shutil.rmtree(output_dir)

    os.mkdir(output_dir)

    odfh = open(output_data_file_path, 'w')

    in_table_def = False
    in_alter_table = False

    cur_table_name = None

    insert_buf = []
    in_insert = False

    for line in ifh:
        if len(line) == 0:
            continue

        if com_regx.match(line):
            continue

        if in_insert:
            if eval_regx.match(line):
                # Discard the insert statement if no values are given.
                # example:
                #  insert into tbl_name (`a`, `b`, `c`)
                #  values;
                in_insert = False
                insert_buf = []
                continue
            insert_buf.append(line.lstrip(" \t").rstrip("\n\r"))
            if eins_regx.match(line):
                in_insert = False
                odfh.write("\n" + " ".join(insert_buf))
                insert_buf = []
            continue

        if in_table_def:
            etable_match = etable_regx.match(line)
            if etable_match:
                in_table_def = False
                continue
            table_defs[cur_table_name].append("" + line.strip("\n"))
            continue

        elif in_alter_table:
            add_match = add_regx.match(line)
            if add_match:
                tbl_last_line = table_defs[cur_table_name][-1]
                table_defs[cur_table_name][-1] = "{},".format(tbl_last_line)
                table_defs[cur_table_name].append("  {}".format(add_match.group(2)))
                continue
            mod_match = mod_regx.match(line)
            if mod_match:
                match_line = mod_match.group(2)
                col_match = col_regx.match(match_line)
                if col_match:
                    col_name = col_match.group(3)
                    for i, tline in enumerate(table_defs[cur_table_name]):
                        tcol_name = col_regx.match(tline).group(3)
                        if col_name == tcol_name:
                            table_defs[cur_table_name][i] = " {},".format(match_line)
                            break
                continue
            in_alter_table = False

        ctable_match = ctable_regx.match(line)
        if ctable_match:
            cur_table_name = ctable_match.group(3)
            table_order.append(cur_table_name)
            table_defs[cur_table_name] = []
            in_table_def = True
            continue

        atable_match = atable_regx.match(line)
        if atable_match:
            cur_table_name = atable_match.group(3)
            in_alter_table = True
            continue

        if ins_regx.match(line):
            if eval_regx.match(line):
                continue
            if not eins_regx.match(line):
                insert_buf.append(line.lstrip(" ").rstrip("\n\r"))
                in_insert = True
            else:
                odfh.write(line)
            continue

    ifh.close()
    odfh.close()

    odufh = open(output_dump_file_path, 'w')
    odafh = open(output_data_file_path, 'r')

    for table_name in table_order:
        odufh.write("CREATE TABLE `{}` (\n{}\n);\n".format(table_name, "\n".join(table_defs[table_name])))

    for line in odafh:
        odufh.write(line)

    odufh.close()
    odafh.close()

    os.unlink(output_data_file_path)

    if echo_results:
        odufh = open(output_dump_file_path, 'r')
        for line in odufh:
            ofh.write(line)
        odufh.close()
        shutil.rmtree(output_dir)
    else:
        ofh.write("done")

    ofh.close()


ctrigger_regx = re.compile("^\/\*.*CREATE.*TRIGGER", re.I)
etrigger_regx = re.compile("END \*\/;;", re.I)
cview_regx = re.compile("^\/\*.*CREATE.*TABLE", re.I)
eview_regx = re.compile("^(\).*ENGINE.*\*\/;)", re.I)
key_regx = re.compile("^(  KEY|\);)", re.I)
ainc_regx = re.compile("auto_increment", re.I)


def mysqldump_to_sqlite(ifh, ofh=None, echo_results=False):
    if ofh is None:
        ofh = sys.stdout

    # Write sqlite header
    ofh.write("PRAGMA synchronous = OFF;\n")
    ofh.write("PRAGMA journal_mode = MEMORY;\n")
    ofh.write("BEGIN TRANSACTION;\n")

    in_trigger = False
    in_view = False
    in_table = False
    cur_table_name = None
    a_inc = False
    first_in_table = False
    prev = None
    keys = {}
    for line in ifh:
        line = re.sub(",$", "", line)
        if in_trigger:
            etrigger_match = etrigger_regx.search(line)
            if etrigger_match:
                line = re.sub("\*\/", "", line)
                ofh.write(line)
                in_trigger = False
                continue
            ofh.write(line)
            continue
        if in_view:
            eview_match = eview_regx.search(line)
            if eview_match:
                in_view = False
                continue
            ofh.write(line)
        if in_table:
            #print("in table")
            if etable_regx.search(line):
                #print("found end table")
                if prev is not None and len(prev) > 0:
                    if first_in_table:
                        ofh.write(prev)
                        first_in_table = False
                    else:
                        ofh.write(",{}".format(prev))
                in_table = False
                prev = ""
                ofh.write(");\n")
                continue
            if not re.search("^  ", line, re.I):
                #print("invalid line")
                continue
            if re.search("^  FULLTEXT KEY", line, re.I):
                line = re.sub(".+KEY", "  KEY")
            if re.search(" (PRIMARY )?KEY", line, re.I):
                line = re.sub("\([0-9]+\)", "", line, re.I)
            if a_inc == True and re.search("PRIMARY KEY", line, re.I):
                #print("a_inc and primary key")
                continue
            key_match = key_regx.search(line)
            #print("key match")
            #print(key_match)
            if key_match is None:
                #print("not key match")
                if ainc_regx.search(line):
                    a_inc = True
                    line = re.sub("auto_increment", "PRIMARY KEY AUTOINCREMENT", line, flags=re.I)
                line = re.sub("unique\s+key\s+`.*`\s+", "UNIQUE ", line, flags=re.I)
                line = re.sub("character\s+set\s+[^ ]+", "", line, flags=re.I)
                line = re.sub("default\s+current_timestamp\s+on\s+update\s+current_timestamp", "", line, re.I)
                line = re.sub("collate\s+[^ ]+( |$)", "", line, flags=re.I)
                line = re.sub("enum[^)]+\)", "text ", line, flags=re.I)
                line = re.sub("set\([^)]+\)", "text ", line, flags=re.I)
                line = re.sub("unsigned", "", line, flags=re.I)
                line = re.sub("` [^ ]*(INT|int)[^ ]*", "` integer", line, flags=re.I)
                if prev is not None and len(prev) > 0:
                    if first_in_table:
                        ofh.write(prev)
                        first_in_table = False
                    else:
                        ofh.write(",{}".format(prev))
                prev = line
            else:
                #print("key match")
                if prev is not None and len(prev) > 0:
                    if first_in_table:
                        ofh.write(prev)
                        first_in_table = False
                    else:
                        ofh.write(",{}".format(prev))
                prev = ""
                if key_match.group(1) == ");":
                    ofh.write(line)
                else:
                    index_name = ""
                    index_name_arr = re.findall("\`[^`]+", line)
                    if len(index_name_arr):
                        index_name = index_name_arr[0][1:]
                    index_key = ""
                    index_key_arr = re.findall("\([^()]+", line)
                    if len(index_key_arr):
                        index_key = index_key_arr[0][1:]
                    if cur_table_name not in keys.keys():
                        keys[cur_table_name] = ""
                    keys[cur_table_name] += "CREATE INDEX \"{}_{}\" ON \"{}\" ({});\n".format(cur_table_name, index_name, cur_table_name, index_key)

            continue
        # Skip comments
        com_match = com_regx.search(line)
        if com_match:
            continue
        # Write insert statements directly
        ins_match = ins_regx.search(line)
        if ins_match:
            prev = ""
            line = line.replace("\\n", "\n")
            line = line.replace("\\r", "\r")
            line = line.replace("\\'", "\"")
            ofh.write(line)
            continue
        ctable_match = ctable_regx.search(line)
        if ctable_match:
            #print("table match")
            cur_table_name = ctable_match.group(3)
            ofh.write(line)
            a_inc = False
            first_in_table = True
            in_table = True
            prev = ""
            continue

    for table in sorted(keys.keys()):
        ofh.write(keys[table])
    ofh.write("END TRANSACTION;")
    ofh.close()

if __name__ == "__main__":
    echo_results = False
    ifh = None
    ofh = None
    if ARGS.file and len(ARGS.file):
        ifh = open(ARGS.file[0], 'r')
        echo_results = ARGS.echo
    else:
        stdin_st_mode = os.fstat(sys.stdin.fileno()).st_mode
        if stat.S_ISFIFO(stdin_st_mode):
            ifh = sys.stdin
            echo_results = True
        else:
            print("You must specify a filename if you don't pipe data to this script")
            sys.exit(-1)
    ofh = sys.stdout

    if ARGS.phpmyadmin:
        phpmyadmin_to_mysql(ifh, ofh, echo_results)
        sys.exit(0)
    elif ARGS.mysql:
        mysqldump_to_sqlite(ifh, ofh, echo_results)
        sys.exit(0)
    else:
        print("Please choose mode...")
        sys.exit(-1)
