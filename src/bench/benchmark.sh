#!/bin/sh -xe
# Adapted from https://www.jamescoyle.net/how-to/1131-benchmark-mysql-server-performance-with-sysbench

#check for required parameters
if [ $# -eq 0 ]; then
    echo "Usage: $0 <mysql_host> <mysql_user> <mysql_password> <mysql_db>"
    exit 1
fi

# Set mysql connection parameters from command line parameters
MYSQL_OPTS="--mysql-host=$1 --mysql-user=$2 --mysql-password=$3 --mysql-db=$4"

GENERAL_OPTS='--threads=6 --events=0 --time=60'

TEST_OPTS='--table-size=1000000'
TEST_NAME=db_read_write


ALL_OPTS="$MYSQL_OPTS $GENERAL_OPTS $TEST_OPTS"

sysbench $ALL_OPTS $TEST_NAME prepare
sysbench $ALL_OPTS $TEST_NAME run
sysbench $ALL_OPTS $TEST_NAME cleanup
