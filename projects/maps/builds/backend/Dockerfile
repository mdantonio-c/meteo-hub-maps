FROM rapydo/backend:3.0

ARG CURRENT_UID
RUN test -n "$CURRENT_UID"

ARG CURRENT_GID
RUN test -n "$CURRENT_GID"

ENV APIUSER developer
RUN usermod -u $CURRENT_UID $APIUSER \
    && groupmod -og $CURRENT_GID $APIUSER

RUN pip3 install --upgrade passlib
    
