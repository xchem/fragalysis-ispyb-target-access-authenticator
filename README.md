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

That returns the following properties, each value being a string ina **200** response: -

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
  "target_access": [ "lb-00000", "lb-000001" ]
}
```

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

---

[black]: https://black.readthedocs.io/en/stable
[commitizen]: https://commitizen-tools.github.io/commitizen/
[conventional commit]: https://www.conventionalcommits.org/en/v1.0.0/
[fastapi]: https://fastapi.tiangolo.com
[poetry]: https://python-poetry.org
[pre-commit]: https://pre-commit.com
