# Mistral Meteo-Tiles maps

## HOWTO Get started

#### Clone the project

```
$ git clone https://gitlab.hpc.cineca.it/mistral/meteo-hub-maps.git
$ cd meteo-hub-maps
$ git checkout 0.6
```

### Install the controller

```
$ sudo pip3 install --upgrade git+https://github.com/rapydo/do.git@2.4`

$ rapydo install
```

### Init & start

```
$ rapydo init
$ rapydo pull
$ rapydo start
```

First time it takes a while as it builds some docker images. Finally, you should see:

```
...
Creating maps_backend_1  ... done
2022-02-23 08:27:33,013 INFO    Stack started
```

In dev mode you need to start api service by hand. Open a terminal and run:
`$ rapydo shell backend --default`

Now open your browser and type http://localhost:8080/api/status in the address bar, if the stack is running you will read a "Server is alive" message

In production mode the api service will automatically start and proxied by a nginx server.

## Maps API

The HTTP APIs, written in Python by using the Flask framework, are used to serve forecast maps (and corresponding legends) as well as information about the latest available run of both forecast and multilayer maps.
All the endpoints are described as OpenAPI specifications and provided by the /api/specs endpoint

## Tiles of multilayer maps

Tiles of multilayer maps are not served by the HTTP APIs, but are provided as static files by a nginx server, external to this application.

As example, the core nginx configuration used to serve tiles is reported:

```
server {
    location /tiles/00-lm2.2/ {
        alias /path/on/the/disk/Tiles-00-lm2.2.web/;
    }
    location /tiles/12-lm2.2/ {
        alias /path/on/the/disk/Tiles-12-lm2.2.web/;
    }
    location /tiles/00-lm5/ {
        alias /path/on/the/disk/Tiles-00-lm5.web/;
    }
    location /tiles/12-lm5/ {
        alias /path/on/the/disk/Tiles-12-lm5.web/;
    }
    location /tiles/00-iff/ {
        alias /path/on/the/disk/Tiles-00-iff.web/;
    }
    location /tiles/12-iff/ {
        alias /path/on/the/disk/Tiles-12-iff.web/;
    }
}
```

## Data organization

```
├── CLUSTER_NAME
│    ├── DEV
│    │     ├── Magics-00-lm2.2.web
│    │     │     ├── 2022022300.READY
│    │     │     ├── Centro_Italia
│    │     │     │   ├── product-name
│    │     │     │   │   ├── product-name.2022022300.0000.png
│    │     │     │   │   ├── product-name.2022022300.0001.png
│    │     │     │   │   ├── ...
│    │     │     │   │   └── ...
│    │     │     │   └── ...
│    │     │     ├── Italia
│    │     │     ├── ...
│    │     │     └── legeds
│    │     ├── Magics-00-lm5.web
│    │     │     ├── ...
│    │     │     └── ...
│    │     ├── Magics-12-lm2.2.web
│    │     │     ├── ...
│    │     │     └── ...
│    │     ├── Magics-12-lm5.web
│    │     │     ├── ...
│    │     │     └── ...
│    │     ├── PROB-00-iff.web
│    │     │     ├── ...
│    │     │     └── ...
│    │     ├── PROB-12-iff.web
│    │     │     ├── ...
│    │     │     └── ...
│    │     ├── Tiles-00-lm2.2.web
│    │     │     ├── ...
│    │     │     └── ...
│    │     ├── Tiles-00-lm5.web
│    │     │     ├── ...
│    │     │     └── ...
│    │     ├── Tiles-12-lm2.2.web
│    │     │     ├── ...
│    │     │     └── ...
│    │     ├── Tiles-12-lm5.web
│    │     │     ├── ...
│    │     │     └── ...
│    ├── PROD
│    │     ├── ...
│    │     └── ...
```
