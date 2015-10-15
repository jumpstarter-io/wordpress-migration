#!/usr/bin/env python2

#####
# This script is written to work with phpmyadmin sql dumps using the following configuration:
#
# output compatibility: NONE
# Syntax to use when inserting data:
#    include column names in every INSERT statement
#      Example: INSERT INTO tbl_name (col_A,col_B,col_C) VALUES (1,2,3)
#####

import sys
import os
import re
import shutil
import stat

table_order = []
table_defs = {}

ctable_regx = re.compile("^(\s+)?create\s+table\s+(`|\"|')([^`\"']+)(`|\"|')\s+\($", re.I)
etable_regx = re.compile("^(\s+)?\)\s+.*;$", re.I)
atable_regx = re.compile("^(\s+)?alter\s+table\s+(`|\"|')([^`\"']+)(`|\"|')$", re.I)
apk_regx = re.compile("^(\s+)?add\s+primary\s+key\s+\((`|\"|')([^`\"']+)(`|\"|')\)(,|;)$", re.I)
add_regx = re.compile("^(\s+)?add\s+(.*)(,|;)$", re.I)
mod_regx = re.compile("^(\s+)?modify([^,]+).*(,|;)$", re.I)
col_regx = re.compile("^(\s+)?(`|\"|')([^`\"']+)(`|\"|')", re.I)
ins_regx = re.compile("^(\s+)?insert\s+into.*$", re.I)
eins_regx = re.compile(".*\)(\s+)?;(\s+)?", re.I)
eval_regx = re.compile(".*values(\s+)?;", re.I)
com_regx = re.compile("^(\s+)?(#|/\*)", re.I)

if __name__ == "__main__":
    fh = None
    echo_results = False
    
    mode = os.fstat(sys.stdin.fileno()).st_mode
    if stat.S_ISFIFO(mode):
        # data is piped into the script
        fh = sys.stdin
        # since we got data on stdin we assume that the data will be piped from
        # this script to another one.
        echo_results = True
    else:
        # data should be read from a specified file
        if len(sys.argv) < 2:
            print("Please supply a filename to read from!")
            sys.exit(1)
        in_file_name = sys.argv[1]
        fh = open(in_file_name, 'r')
        # decide if we should echo the result or not
        if len(sys.argv) == 3:
            echo_results = True
    
    output_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")
    output_data_file_path = os.path.join(output_dir, "data.sql")
    output_dump_file_path = os.path.join(output_dir, "dump.sql")
    
    if os.path.exists(output_dir) and os.path.isdir(output_dir):
        shutil.rmtree(output_dir)

    os.mkdir(output_dir)

    odfh = open(output_data_file_path, 'w')

    in_table_def = False
    in_alter_table = False

    cur_table_name = None

    insert_buf = []
    in_insert = False
    
    for line in fh:
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

    fh.close()
    odfh.close()

    ofh = open(output_dump_file_path, 'w')
    odfh = open(output_data_file_path, 'r')
    
    for table_name in table_order:
        ofh.write("CREATE TABLE `{}` (\n{}\n);\n".format(table_name, "\n".join(table_defs[table_name])))

    for line in odfh:
        ofh.write(line)

    ofh.close()
    odfh.close()

    os.unlink("output/data.sql")

    if echo_results:
        ofh = open(output_dump_file_path, 'r')
        for line in ofh:
            print(line)
        ofh.close()
        shutil.rmtree(output_dir)
    else:
        print("done")
    
    
