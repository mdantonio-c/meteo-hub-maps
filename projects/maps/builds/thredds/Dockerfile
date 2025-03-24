FROM unidata/thredds-docker:5.6


COPY ./catalog.xml /usr/local/tomcat/catalog.xml
# COPY ./tomcat-users.xml /usr/local/tomcat/conf/tomcat-users.xml
COPY ./init.sh ./init.sh
ENTRYPOINT [ "sh", "-c" ]