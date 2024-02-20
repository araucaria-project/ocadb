# OCM (former OCA) Observatory Database

This repository contains the code for the OCA Observatory Database. It is a part of the OCA software environment.

We use the monorepo approach, the project can be used in various scenarios:
* As a package serving data from local database (default import). The code from `ocadb` package is a startpoint.
* As a Command Line Interface (CLI) for the database. The `ocadb` utility is installed with the package.
* As an HTTP API server. The FastAPI-based server is in the `api` package. To install all dependencies, 
  use the `server` extra, e.g. `pip install ocadb[server]`.
* As a Web Application. The `frontend` package contains Vue.js web application. To install all dependencies, 
  use the `server` extra, e.g. `pip install ocadb[server]`. The application utilizes the API server.


### Docker Compose
Provided `docker-compose.yml` file allows to run the database, API server and web application in Docker containers for 
development purposes. Use `docker-compose up` to start the services. The following ports are exposed:
* 8084 - API server
* 8085 - Web application
* 27017 - MongoDB


### Project Initialization
This section describes the steps which have been done to initialize the project.
This section is for informational purposes only, developers do not need to repeat these steps.

Project has been initialized by `poetry` tool with the following command:
```bash
poetry new ocadb
```
Then `api` packages have been added manually. 
The `docker-compose.yml` and `api/Dockerfile` files have been created manually as well.

For the web application, the `frontend` Vue.js subproject has been created using dockerized Node.js environment:
```bash
docker run -it --rm -v ${PWD}/frontend:/app node:20 /bin/bash
```
Then, inside the container:
```bash
  npm install -g @vue/cli
  cd /app
  vue create .
```
