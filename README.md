# The Fragalysis ISPyB Target Access Authenticator

![GitHub Release](https://img.shields.io/github/v/release/xchem/fragalysis-ispyb-target-access-authenticator?include_prereleases)

[![latest](https://github.com/xchem/fragalysis-ispyb-target-access-authenticator/actions/workflows/latest.yaml/badge.svg)](https://github.com/xchem/fragalysis-ispyb-target-access-authenticator/actions/workflows/latest.yaml)
[![tag](https://github.com/xchem/fragalysis-ispyb-target-access-authenticator/actions/workflows/tag.yaml/badge.svg)](https://github.com/xchem/fragalysis-ispyb-target-access-authenticator/actions/workflows/tag.yaml)

[![License](http://img.shields.io/badge/license-Apache%202.0-blue.svg?style=flat)](https://github.com/xchem/fragalysis-ispyb-target-access-authenticator/blob/master/LICENSE.txt)

[![Conventional Commits](https://img.shields.io/badge/Conventional%20Commits-1.0.0-yellow.svg)](https://conventionalcommits.org)
[![pre-commit](https://img.shields.io/badge/pre--commit-enabled-brightgreen?logo=pre-commit&logoColor=white)](https://github.com/pre-commit/pre-commit)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
[![Packaged with uv](https://img.shields.io/badge/packaging-uv-cyan.svg)](https://docs.astral.sh/uv/)

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

The stack's _contract_ with the TA authenticator requires the following endpoints
from any implementation of the authenticator: -

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

### `/users/{tas}` **[GET]**

The reverse of the target access query. Given a target access string the
authenticator returns a count and the **set** of user IDs (ISPyB `login` values)
that are members of it: -

```json
{
  "count": 1,
  "users": [ "abc12345" ]
}
```

>   As with the target-access endpoint the client must provide a `X_TAAQueryKey`
    header value that matches the `TAA_QUERY_KEY` environment value.

A **400** is returned if the value provided is not a target access string, and a
**503** if the authenticator cannot reach the underlying (ISPyB) service at all.

An empty set (`{"count": 0, "users": []}`) is returned when the visit has no
members, when the visit is not known, **and** when the query itself fails - at
the time of writing our database account is not permitted to execute the
underlying `retrieve_persons_for_session` procedure. The caller cannot tell
those cases apart, so a query failure is logged as a warning by the
authenticator (and is visible with `users.py` in the container).

Unlike the target-access endpoint, results are **not** cached, so every request
results in a query of the underlying service.

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
A number of debug tools are shipped with the image. If you can _shell_ into
the corresponding container you can run them from the command line.
The authenticator is typically deployed in a kubernetes **Pod** as
a container called **ta-authenticator**, co-located with a **memcached**
container (in the same **Pod**).

To display detailed "global" stats for the authentication container you can run: -

    ./stats.py

You can display (but not get) the cached target-access strings
for a given user (along with the cache collection time and age)
by providing a username to the `tas.py` utility: -

    ./tas.py abc12345

You can clear individual user records with `clear.py`.
This simply clears the cache, forcing a new collection of
values at the next opportunity: -

    ./clear.py abc12345

`get.py uses the local API to simulate a stack query which will refresh
the cache if it required while also printing the results; -

    ./get.py 'dave lister'
    '{"count":3,"target_access":["aa00000-1","aa00000-254","aa00000-2"]}'

`users.py` goes the other way - given a target access string it prints the
**raw** ISPyB response for the people who are members of it, by calling the
`retrieve_persons_for_session` stored procedure directly rather than going
through the local API. Use it to see what the database actually returns, or
why the call is being refused: -

    ./users.py lb12345-1

### HTTP debug
If an **Ingress** is deployed an HTTP service can be used to invoke the container's
statistics endpoint on port `8081.` This is a `text/plain` response replicating
the behaviour of the in-container stats utility described above.

If a header key is required for the statistics (an option), it is usually a [shortuuid]
value. If a key is required you will need to provide this in your request header
as the value to `X-TAAStatsKey`. In this example we use [httpie] to get the stats from
an authenticator deployed with the key `24pp4CmJP2wCz2EiGgCctG`: -

    http https://authenticator.example.com X-TAAStatsKey:24pp4CmJP2wCz2EiGgCctG

And the same thing using `curl`: -

    curl https://authenticator.example.com -H X-TAAStatsKey:24pp4CmJP2wCz2EiGgCctG

## Contributing
The project uses: -

- [pre-commit] to enforce linting of files prior to committing them to the
  upstream repository
- [Commitizen] to enforce a [Conventional Commit] commit message format
- [Black] as a code formatter
- [uv] as a package manager (for the b/e)

You **MUST** comply with these choices in order to  contribute to the project.

To get started review the pre-commit utility and the conventional commit style
and then set-up your local clone by following the **Installation** and
**Quick Start** sections: -

    uv sync
    uv run pre-commit install -t commit-msg -t pre-commit

Now the project's rules will run on every commit, and you can check the
current health of your clone with: -

    uv run pre-commit run --all-files

`uv sync` creates a `.venv` in the clone, installing the project's dependencies
and the development group from the `uv.lock` file. Prefix commands with
`uv run` to use it, or activate it yourself with `source .venv/bin/activate`.
The Python version is pinned by the `.python-version` file, and matches the
version used by the container image.

If you change a dependency in `pyproject.toml` run `uv lock` and commit the
updated `uv.lock` - the image build uses `uv sync --locked`, which fails if the
two are out of step.

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

To get some test results, if you've set the `TAA_ENABLE_DAVE_LISTER` environment
variable to `yes`, you can get some realistic test results with that username.
This is not a real user, it is simply one that the authentication "simulates" with
a fixed set of target access strings: -

    http localhost:8080/target-access/dave%20lister 'x-taaquerykey:blob1234'

You can execute the ping and version endpoints too...

    http localhost:8080/ping/

    http localhost:8080/version/

You can terminate the local installation with: -

    docker compose down

## The "mock" authenticator
We have also developed a "mock" authenticator that "looks and feels" like the
_real thing_. It offers the same API, can run locally, and is configured
using text files that list users and their target-access strings. It does not
need an ISPyB service but behaves as though it has one.

See: -

- https://github.com/xchem/fragalysis-mock-target-access-authenticator

---

[black]: https://black.readthedocs.io/en/stable
[commitizen]: https://commitizen-tools.github.io/commitizen/
[conventional commit]: https://www.conventionalcommits.org/en/v1.0.0/
[environment variables]: https://docs.docker.com/compose/how-tos/environment-variables/set-environment-variables/
[fastapi]: https://fastapi.tiangolo.com
[fragalysis-backend]: https://github.com/xchem/fragalysis-backend
[httpie]: https://httpie.io
[uv]: https://docs.astral.sh/uv
[pre-commit]: https://pre-commit.com
[shortuuid]: https://pypi.org/project/shortuuid/
