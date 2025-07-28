# Design
We use Python's [FastAPI] framework to offer a lightweight implementation of an
HTTP service that is expected to be deployed as a **Pod** and **Service** in
kubernetes.

The application is deployed as a **container** in a **Pod**, and shares the Pod
with a memcached container (available on `localhost`). COnfiguration is via
*environment variables* that are handled by `config.py` with code that is considered
*common* in `common.py`.

It borrows the ISPyB access logic present in the stack's original `security` module
and has a copy of the remote ISPyB logic module `remote_ispyb_connector.py`.

The ISPyB Target Access Authenticator (the TA Authenticator) provides responses to
**GET** requests from the `/target-access/{username}` endpoint. The response is a
**Set** of *Proposals* and *Visits* available to the named user. A target access string
(TAS) consists of a concatenation of a *code* (e.g. `lb`), a *proposal number*
(e.g. `12345`), and a *visit number* (e.g. `125`). For example `lb12345-125`.

These strings are used by the Diamond Light Source Fragalysis Stack to
authenticate a user's access to Targets.

The authenticator does what the original stack security module did ...
it accesses a remote ISPyB MySQL database using an SSH tunnel using credentials
provided by the following environment variables: -

-   `TAA_ISPYB_HOST`
-   `TAA_ISPYB_USER`
-   `TAA_ISPYB_PASSWORD`
-   `TAA_SSH_HOST`
-   `TAA_SSH_USER`
-   `TAA_SSH_PASSWORD` or `TAA_SSH_PRIVATE_KEY_FILENAME`

>   THE `TAA_SSH_PASSWORD` exists simply for backwards compatibility although
    using a password no longer works. Instead, a private key file must now be provided.

Other variables that can be set that have (sensible) defaults are: -

-   `TAA_ISPYB_DB` (**"ispyb"**)
-   `TAA_ISPYB_PORT` (**"4306"**)
-   `TAA_ISPYB_CONN_INACTIVITY` (**"360"**)

The `TAA_SSH_PRIVATE_KEY_FILENAME` is interpreted as an absolute path and filename
within the application container and you are expected to have mapped the corresponding
SSH private key file into the container (using a **ConfigMap**).

Two types of records are cached for each user; a set of TAS values for the user,
and the timestamp the TAS values were collected. The TAS set key is written
to the cache using the URL-encoded value of the username (memcached keys cannot
contain spaces for example). The cache timestamp for the user is the URL-encoded
username prefixed with `timestamp-`.

A query of the underlying ISPyB database is made if there are no records for the
requested user or the user's existing records are *too old*. The maximum age of each
user's cached results is defined by the following container environment variable: -

-   `TAA_CACHE_EXPIRY_MINUTES` (default of **"15"**)

The authenticator also caches the `/ping` response as a ping requires the authenticator
to query the ISPyB database. The age of the cache of a ping response is defined using
the environment variable: -

-   `TAA_PING_CACHE_EXPIRY_SECONDS` (default **"55"** seconds)

# Rules
When a request for the target access strings for a user is made to
`/target-access/{username}` then, if...

1.  There is no cache for the user (OR)
2.  There is no cache timestamp for the user (OR)
3.  A user's timestamp is too old

...the app first attempts to collect new target access strings from the configured
remote ISPyB database before returning the results to the caller.

After every attempt to load new ISPyB results into the cache (successful or not)
a new *cache timestamp* is written to the cache for the user. As a result,
even if ISPyB returns an empty set of results for the user it is unlikely
that another ISPyB query will occur for at least 15 minutes (the default cache expiry).

The cached values are never discarded but the underlying [memcached] engine *can*
discard records, especially when storage is limited. Therefore we have to be aware that
previously cached values may be lost, and the above rules satisfy this need.

It is important to realise that as the memcached container shares the same Pod
as the application, any Pod restart will result in the cache being lost.

For diagnostic purposes the number of calls to `/ping` and `/target-access/{username}`
and the corresponding number of upstream ISPyB database calls are counted (and stored
in the cache). These values are made visible by some debug modules that are
provided with the app.

# Debug modules
As well as the main TA authenticator app the container image also contains a small
number of utilities to help gather diagnostics.

The `stats.py` module provides general [memcached] stats and statistical information
about the running application. You might find the following for example: -

```
---
ping_status='OK'
ping_count=136/272 (reduction=50%)
query_count=4/45 (reduction=91%)
---
```

The `tas.py` module provides detailed information relating to the cache for a specific
user. This tool lets you see the encoded username, any date relating to the cached
data for that user, a simplified display of cache age and the set of target access
strings. You might find the following for example: -

```
  Username: 'wmu55374' (wmu55374)
 Collected: 2025-07-28T15:18:40.871881+00:00
 Cache age: an hour
No. of TAS: 2
   TAS Set:
{'lb12345-0', 'lb12345-1'}
```

---

[fastapi]: https://fastapi.tiangolo.com
[memcached]: https://memcached.org
