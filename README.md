# The Fragalysis ISPyB Target Access Authenticator

![GitHub Release](https://img.shields.io/github/v/release/xchem/fragalysis-ispyb-target-access-authenticator?include_prereleases)

[![build](https://github.com/xchem/fragalysis-ispyb-target-access-authenticator/actions/workflows/build.yaml/badge.svg)](https://github.com/xchem/fragalysis-ispyb-target-access-authenticator/actions/workflows/build.yaml)
[![tag](https://github.com/xchem/fragalysis-ispyb-target-access-authenticator/actions/workflows/tag.yaml/badge.svg)](https://github.com/xchem/fragalysis-ispyb-target-access-authenticator/actions/workflows/tag.yaml)

[![License](http://img.shields.io/badge/license-Apache%202.0-blue.svg?style=flat)](https://github.com/xchem/fragalysis-ispyb-target-access-authenticator/blob/master/LICENSE.txt)

[![Conventional Commits](https://img.shields.io/badge/Conventional%20Commits-1.0.0-yellow.svg)](https://conventionalcommits.org)
[![pre-commit](https://img.shields.io/badge/pre--commit-enabled-brightgreen?logo=pre-commit&logoColor=white)](https://github.com/pre-commit/pre-commit)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
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

### `/version` **[GET]**

That returns a **200** response with the following properties: -

```json
{
  "version": "1.0.0",
  "kind": "ISPYB",
  "name": "XChem Python FastAPI TAS Authenticator"
}
```

The stack can use the response as it sees fit, but it might want to display
the response in the UI.

### `/target-access/{username}` **[GET]**

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

### `/ping` **[GET]**

```json
{
  "ping": "OK"
}
```

It returns a **200** response with a `ping` string property that is `OK` if the
authenticator is able to connect to the underlying (ISPyB) service. The string
is not `OK` if there are problems.

### In-container debug
Two debug modules are contained in the image: `stats.py` and `tas.py`. To displayed
detailed stats for the authentication container you can shell-into it and display
statistics: -

    ./stats.py

Tou can also display the cached target-access strings for a given user but providing
their username to the `tas.py` utility: -

    ./tas.py 'dave lister'

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
[poetry]: https://python-poetry.org
[pre-commit]: https://pre-commit.com
