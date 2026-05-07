FROM unidata/thredds-docker:5.8

# Create THREDDS data directories at build time
RUN mkdir -p /usr/local/tomcat/content/thredds/public/MER/water-level-arpae && \
    mkdir -p /usr/local/tomcat/content/thredds/public/MER/water-level-dpc && \
    chmod -R 755 /usr/local/tomcat/content/thredds/public/MER

# Copy THREDDS catalog configuration
COPY ./catalog.xml /usr/local/tomcat/content/thredds/catalog.xml

# Ensure catalog is accessible
RUN chmod 644 /usr/local/tomcat/content/thredds/catalog.xml

ENTRYPOINT ["/entrypoint.sh"]
CMD ["catalina.sh", "run"]