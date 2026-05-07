FROM unidata/thredds-docker:5.8

# Create THREDDS data directories at build time
RUN mkdir -p /usr/local/tomcat/content/thredds/public/MER/water-level-arpae && \
    mkdir -p /usr/local/tomcat/content/thredds/public/MER/water-level-dpc && \
    chmod -R 755 /usr/local/tomcat/content/thredds/public/MER

# Copy THREDDS catalog configuration
COPY ./catalog.xml /usr/local/tomcat/content/thredds/catalog.xml
COPY ./threddsConfig.xml /usr/local/tomcat/content/thredds/threddsConfig.xml
COPY ./wmsConfig.xml /usr/local/tomcat/content/thredds/wmsConfig.xml

# Ensure configs are accessible
RUN chmod 644 /usr/local/tomcat/content/thredds/catalog.xml && \
    chmod 644 /usr/local/tomcat/content/thredds/threddsConfig.xml && \
    chmod 644 /usr/local/tomcat/content/thredds/wmsConfig.xml

# Prevent java.util.prefs fallback warnings and avoid runtime permission issues.
RUN mkdir -p /usr/local/tomcat/content/thredds/javaUtilPrefs/.systemPrefs && \
    chmod -R 755 /usr/local/tomcat/content/thredds/javaUtilPrefs

ENTRYPOINT ["/entrypoint.sh"]
CMD ["catalina.sh", "run"]