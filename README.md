# The Fragalysis ISPyB Target Access Authenticator

![GitHub release (latest by date)](https://img.shields.io/github/v/release/xchem/fragalysis-ispyb-target-access-authenticator)

[![build](https://github.com/xchem/fragalysis-ispyb-target-access-authenticator/actions/workflows/build.yaml/badge.svg)](https://github.com/xchem/fragalysis-ispyb-target-access-authenticator/actions/workflows/build.yaml)

[![License](http://img.shields.io/badge/license-Apache%202.0-blue.svg?style=flat)](https://github.com/xchem/fragalysis-ispyb-target-access-authenticator/blob/master/LICENSE.txt)

[![Conventional Commits](https://img.shields.io/badge/Conventional%20Commits-1.0.0-yellow.svg)](https://conventionalcommits.org)
[![pre-commit](https://img.shields.io/badge/pre--commit-enabled-brightgreen?logo=pre-commit&logoColor=white)](https://github.com/pre-commit/pre-commit)
[![Packaged with Poetry](https://img.shields.io/badge/packaging-poetry-cyan.svg)](https://python-poetry.org/)

The ISPyB authenticator provides the Fragalysis Stack with a centralised service that
can be utilised bny any number of stacks, and yields Target Access Strings based on User.
It essentially replaces the stack internal **security** modules's ISPyB query mechanism.

The service is deployed into Kubernetes, typically in its own Namespace, along
with a Service definition to allow in-cluster queries. By extracting the security
logic from the Stack administrators can deploy custom authentication implementations
using services other than ISPyB. For example you may control Target Access from
PostgreSQL database. If so, you simply have to deploy your own access implementation -
all it has to do is provide the same service. The choice of authentication
implementation is yours. You could for example  deploy a _dummy_ service for testing that
has a built-in (hard-coded) set of Target Access strings and users and it allows
you to develop locally (offline) without needing to connect to any _real_
underlying service.

Any service implementation can be deployed, this one provides access to ISPyB
using a container image based on Python and [FastAPI].

The authentication logic's _contract_ requires the following endpoints: -

-   `/version` **GET**

That returns the following properties, each value being a string in a **200** response: -

```json
{
  "version": "1.0.0",
  "kind": "ISPYB",
  "name": "XChem ISPyB Authenticator"
}
```

A stack requests Target Access Strings based on URL-encoded username strings,
and returns an array of Target Access Strings the user is entitles to access.
The response should be a **200** and a **404** for usernames
that are not known: -

-   `/target-access/{username}` **GET**

```json
{
  "count": 2,
  "target_access": [ "lb-00000", "lb-000001" ]
}
```

>   For a query to be successful the client must provide a `X_TAAQueryKey` header value
    that matches the `TAA_QUERY_KEY` environment value supplied to the image.
    This proves a crude but effective security mechanism that prevents queries without
    providing a pre-defined key.

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
The ISPyB Target Access Authenticator (the TAA) provides responses to **GETS** from the
`/target-access/{username}` endpoint that is a list of **Proposals** and **Visits**
(e.g. `lb-00000-0`). These are used by the Diamond Light Source Fragalysis Stack to
authenticate a user's access to Targets. It does this my communicating with a
remote MySQL database over SSH using credentials provided by the following container
environment variables: -

-   ISPYB_HOST
-   ISPYB_PORT
-   ISPYB_USER
-   ISPYB_PASSWORD
-   SSH_HOST
-   SSH_USER
-   SSH_PASSWORD or SSH_PRIVATE_KEY_FILENAME

If the SSH_PRIVATE_KEY_FILENAME is used (rather than SSH_PASSWORD) you are expected
to have mapped the SSH key file into the container.

The TAA maintains a cache of collected target access strings using a co-located memcached
container. The content of the cache is always returned, while the TAA regularly
tries to synchronise the cache with any result sis gets from the ISPyB database.
The TAA attempts to communicate with the underlyign IPSyB database after the
current data is considered to have expired (see **Rules** below). The expiry time
is based on the number of minutes set in the following environment variable: -

-   CACHE_EXPIRY_MINUTES (default of 2)

The cache contains two records of information for each user: -

1.  The list of **target access strings**, indexed by url-encoded username
2.  A UTC **timestamp** for the time a cache update attempt was made (successful or otherwise)

Rules: -

**If user's timestamp has expired** (or the user cache has no timestamp)
the app attempts to collect new target access strings from the remote
ISPyB database. If the database returns some records they replace the user's
cache content, otherwise the cache content for the user is left untouched.

After every attempt to refresh the cache for the user (successful or otherwise)
a new *timestamp* is written to the cache for the user using the key
`timestamp-{url-encoded-username}`.

In this way the app will only try to refresh a user's target access string cache
no more frequently than once every 2 minutes (by default).

Regardless of whether the cache content is updated or not the current cache content
for the user is always returned in the `/target-access` API response.

>   Where possible the original Fragalysis modules have been retained here.
    For example we have a `remote_ispyb_connector` module that retains the same logic
    as its original modules in the [fragalaysis-backend]. This eases developer
    transition to the new authentication container.

## Local development
You can build and launch the code using the `docker-compose.yml` file.
and make requests to the service via `http:8080/version`
and `http:8080/target-access/dave%20lister`: -

    docker compose up --build --detach

In order to use the target access endpoint, which relies on a pre-shared key for
authentication, you will need to provide the key via the request header
`X-TAAQueryKey`. With the docker services started you can make a target access query
for the built-in test user with `httpie`: -

    http localhost:8080/target-access/dave%20lister 'x-taaquerykey:blob1234'

---

[black]: https://black.readthedocs.io/en/stable
[commitizen]: https://commitizen-tools.github.io/commitizen/
[conventional commit]: https://www.conventionalcommits.org/en/v1.0.0/
[fastapi]: https://fastapi.tiangolo.com
[fragalysis-backend]: https://github.com/xchem/fragalysis-backend
[poetry]: https://python-poetry.org
[pre-commit]: https://pre-commit.com
