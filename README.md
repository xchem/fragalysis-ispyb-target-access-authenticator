# The Fragalysis ISPyB Target Access Authenticator

![GitHub Release](https://img.shields.io/github/v/release/xchem/fragalysis-ispyb-target-access-authenticator?include_prereleases)

[![build](https://github.com/xchem/fragalysis-ispyb-target-access-authenticator/actions/workflows/build.yaml/badge.svg)](https://github.com/xchem/fragalysis-ispyb-target-access-authenticator/actions/workflows/build.yaml)
[![tag](https://github.com/xchem/fragalysis-ispyb-target-access-authenticator/actions/workflows/tag.yaml/badge.svg)](https://github.com/xchem/fragalysis-ispyb-target-access-authenticator/actions/workflows/tag.yaml)

[![License](http://img.shields.io/badge/license-Apache%202.0-blue.svg?style=flat)](https://github.com/xchem/fragalysis-ispyb-target-access-authenticator/blob/master/LICENSE.txt)

[![Conventional Commits](https://img.shields.io/badge/Conventional%20Commits-1.0.0-yellow.svg)](https://conventionalcommits.org)
[![pre-commit](https://img.shields.io/badge/pre--commit-enabled-brightgreen?logo=pre-commit&logoColor=white)](https://github.com/pre-commit/pre-commit)
[![Packaged with Poetry](https://img.shields.io/badge/packaging-poetry-cyan.svg)](https://python-poetry.org/)

The ISPyB authenticator provides the Fragalysis Stack with a centralised service that
can be utilised by any number of stacks, and yields Target Access Strings based on User.
The authenticator is designed to replace the stack's internal **security** module that is
partly responsible for caching the regular SSH and MySQL ISPyB database access mechanism
that restricts user access to objects in the stack based on their membership of *Proposals*
and *Visits*.

By providing an abstraction of the original security logic in an independent **Pod**
(and **Service**) an administrator can replace it with another with its own implementation.
For example, when testing you could replace the official ISPyB service with a custom
or **mock** implementation that provides a well-known set of responses for your users.
In this way you can develop code and not have to rely on access to the true source
of target access strings.

Any service implementation can be deployed, this one provides remote (SSH) access to
ISPyB using a container image based on Python and [FastAPI].

The stack's _contract_ requires the following endpoints from any implementation
of the authenticator: -

### `/version` **GET**

That returns the following properties, each value being a string in a **200** response: -

```json
{
  "version": "1.0.0",
  "kind": "ISPYB",
  "name": "XChem Python FastAPI TAS Authenticator"
}
```

### `/target-access/{username}` **GET**

A stack requests Target Access Strings from the authenticator based on URL-encoded
usernames, and the authenticator returns a count and an array of those the user is
entitled to access.

The response should be a **200** and a **4XX** for errors: -

```json
{
  "count": 2,
  "target_access": [ "lb00000-1", "lb000001-1" ]
}
```

>   For a query to be successful the client must provide a `X_TAAQueryKey` header value
    that matches the `TAA_QUERY_KEY` environment value supplied to the image.
    This proves a crude but effective protection mechanism that prevents queries from
    clients that have not been supplied with the query key.

### `/ping` **GET**

```json
{
  "ping": "OK"
}
```

It returns a `ping` string property that is `OK` if the service is able to connect to
the underlying (ISPyB) service and something else if there are problems.

## Contributing
The project uses: -

- [pre-commit] to enforce linting of files prior to committing them to the
  upstream repository
- [Commitizen] to enforce a [Conventional Commit] commit message format
- [Black] as a code formatter
- [Poetry] as a package manager (for the b/e)

You **MUST** comply with these choices in order to  contribute to the project.

To get started review the pre-commit utility and the conventional commit style
and then set-up your local clone by following the **Installation** and
**Quick Start** sections: -

    poetry shell
    poetry install --with dev
    pre-commit install -t commit-msg -t pre-commit

Now the project's rules will run on every commit, and you can check the
current health of your clone with: -

    pre-commit run --all-files

## Design
We use Python's [FastAPI] framework to offer a lightweight implementation of an
HTTP service that is expected to be deployed as a **Pod** and **Service** in
kubernetes. It borrows the ISPyB access logic present in the stack's `security` module
and utilises a [memcached] container (co-located in the same Pod) to cache results.

The ISPyB Target Access Authenticator (the TAA) provides responses to **GET** requests
from the `/target-access/{username}` endpoint that is a list of *Proposals* and *Visits*
(e.g. `lb00000-0`). These are used by the Diamond Light Source Fragalysis Stack to
authenticate a user's access to Targets. It does this my communicating with a
remote MySQL database over SSH using credentials provided by the following container
environment variables: -

-   TAA_ISPYB_HOST
-   TAA_ISPYB_PORT
-   TAA_ISPYB_USER
-   TAA_ISPYB_PASSWORD
-   TAA_SSH_HOST
-   TAA_SSH_USER
-   TAA_SSH_PASSWORD or TAA_SSH_PRIVATE_KEY_FILENAME

If the TAA_SSH_PRIVATE_KEY_FILENAME is used (rather than TAA_SSH_PASSWORD) you are expected
to have mapped the SSH key file into the container.

Two types of records are cached for each user, one using the url-encoded username as
a key to record results retrieved from the ISPyB database and a second, using the
url-encoded username with a `timestamp-` prefix, to record the time results were
last collected from ISPyB.

The ISpyB database is queried if there are no records for a user or exiting records
are too old. The maximum age of cached results is based on the number of minutes set
in the following container environment variables: -

-   TAA_CACHE_EXPIRY_MINUTES (default of 2)
-   TAA_PING_CACHE_EXPIRY_SECONDS (default 25 seconds)

The authenticator also caches the `/ping` response as a ping requires the authenticator
to query the ISPyB database.

Rules: -

**If user's timestamp has expired** (or the user cache has no timestamp)
the app attempts to collect new target access strings from the remote
ISPyB database. If the database returns some records they replace the user's
cache content, otherwise the cache content for the user is left unmodified.

After every attempt to refresh the cache for the user (successful or otherwise)
a new *timestamp* is written to the cache for the user using the key
`timestamp-{url-encoded-username}`.

The cached values are never discarded. The current cache is returned to tht caller
until it can be successfully replaced by new results from a fresh ISPyB query.

For each user ISPyB is not queried more often than once in the defined expiry period.
In this way the app will only try to refresh a user's target access string cache
no more frequently than once every 2 minutes (by default).

If the authentication container restarts cache results are lost.

Regardless of whether the cache content is updated or not the current cache content
for the user is always returned in the `/target-access` API response.

>   Where possible the original Fragalysis modules have been retained here.
    For example we have a `remote_ispyb_connector` module that retains the same logic
    as its original modules in the [fragalaysis-backend]. This eases developer
    transition to the new authentication container.

## Local development
There's a `docker-compose.yml` file to deploy the authenticator and memcached.
It also relies on [environment variables] that you can easily set using a `.env` file
(which is excluded from any repository commits).

Build and launch the code using the `docker compose` file: -

    docker compose up --build --detach

We rely on docker compose `extend` capability to use a `base-services.yml` compose file
that is then "sepcialised" by either a `docker-compose.yml` or
`docker-compose-private-key.yml`. The former uses SSH passwords, the latter a
private key file. So, if you want to use a private key file for SSH connections
(and have a `~/.ssh/fragalysis-stack` key-file) run: -

    docker compose --file docker-compose-private-key.yml up --build --detach

In order to use the target access endpoint, which relies on a pre-shared key for
authentication, you will need to provide the key that is set in the docker compose file
via the request header `X-TAAQueryKey` (this is set to `blob1234`)

With the containers running you should be able to query
target access results for a user with `httpie`. Here we query user `abc`
(whose name has to be url encoded): -

    http localhost:8080/target-access/abc 'x-taaquerykey:blob1234'

To get some built-in results, if you've set the `TAA_ENABLE_DAVE_LISTER` environment
variable to `yes`, you can get some realistic test results with that username: -

    http localhost:8080/target-access/dave%20lister 'x-taaquerykey:blob1234'

You can execute the ping and version endpoints too...

    http localhost:8080/ping/

    http localhost:8080/version/

You can terminate the local installation with: -

    docker compose down

---

[black]: https://black.readthedocs.io/en/stable
[commitizen]: https://commitizen-tools.github.io/commitizen/
[conventional commit]: https://www.conventionalcommits.org/en/v1.0.0/
[environment variables]: https://docs.docker.com/compose/how-tos/environment-variables/set-environment-variables/
[fastapi]: https://fastapi.tiangolo.com
[fragalysis-backend]: https://github.com/xchem/fragalysis-backend
[memcached]: https://memcached.org
[poetry]: https://python-poetry.org
[pre-commit]: https://pre-commit.com
