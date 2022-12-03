#!/bin/sh

set -e

GALEX_CONFIGURATION_DIR=/etc/galex
GALEX_CONFIGURATION_FILE=$GALEX_CONFIGURATION_DIR/galex.conf
GALEX_DATA_DIR=/var/lib/galex
GALEX_GROUP="galex"
GALEX_LOG_DIR=/var/log/galex
GALEX_LOG_FILE=$GALEX_LOG_DIR/galex-server.log
GALEX_USER="galex"
ABI=$(rpm -q --provides python3 | awk '/abi/ {print $NF}')

if ! getent passwd | grep -q "^galex:"; then
    groupadd $GALEX_GROUP
    adduser --system --no-create-home $GALEX_USER -g $GALEX_GROUP
fi
# Register "$GALEX_USER" as a postgres user with "Create DB" role attribute
su - postgres -c "createuser -d -R -S $GALEX_USER" 2> /dev/null || true
# Configuration file
mkdir -p $GALEX_CONFIGURATION_DIR
# can't copy debian config-file as addons_path is not the same
if [ ! -f $GALEX_CONFIGURATION_FILE ]
then
    echo "[options]
; This is the password that allows database operations:
; admin_passwd = admin
db_host = False
db_port = False
db_user = $GALEX_USER
db_password = False
addons_path = /usr/lib/python${ABI}/site-packages/galex/addons
" > $GALEX_CONFIGURATION_FILE
    chown $GALEX_USER:$GALEX_GROUP $GALEX_CONFIGURATION_FILE
    chmod 0640 $GALEX_CONFIGURATION_FILE
fi
# Log
mkdir -p $GALEX_LOG_DIR
chown $GALEX_USER:$GALEX_GROUP $GALEX_LOG_DIR
chmod 0750 $GALEX_LOG_DIR
# Data dir
mkdir -p $GALEX_DATA_DIR
chown $GALEX_USER:$GALEX_GROUP $GALEX_DATA_DIR

INIT_FILE=/lib/systemd/system/galex.service
touch $INIT_FILE
chmod 0700 $INIT_FILE
cat << EOF > $INIT_FILE
[Unit]
Description=GalexERP Open Source ERP and CRM
After=network.target

[Service]
Type=simple
User=galex
Group=galex
ExecStart=/usr/bin/galex --config $GALEX_CONFIGURATION_FILE --logfile $GALEX_LOG_FILE
KillMode=mixed

[Install]
WantedBy=multi-user.target
EOF
