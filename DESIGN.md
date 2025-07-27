# Design
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

-   `TAA_ISPYB_HOST`
-   `TAA_ISPYB_USER`
-   `TAA_ISPYB_PASSWORD`
-   `TAA_SSH_HOST`
-   `TAA_SSH_USER`
-   `TAA_SSH_PASSWORD` or `TAA_SSH_PRIVATE_KEY_FILENAME`

Other variables with (sensible) defaults are: -

-   `TAA_ISPYB_DB` (**"ispyb"**)
-   `TAA_ISPYB_PORT` (**"4306"**)
-   `TAA_ISPYB_CONN_INACTIVITY` (**"360"**)

If the `TAA_SSH_PRIVATE_KEY_FILENAME` is used (rather than `TAA_SSH_PASSWORD`) you are expected
to have mapped the SSH key file into the container.

Two types of records are cached for each user, one using the url-encoded username as
a key to record results retrieved from the ISPyB database and a second, using the
url-encoded username with a `timestamp-` prefix, to record the time results were
last collected from ISPyB.

The ISpyB database is queried if there are no records for a user or exiting records
are too old. The maximum age of cached results is based on the number of minutes set
in the following container environment variables: -

-   `TAA_CACHE_EXPIRY_MINUTES` (default of **"2"**)
-   `TAA_PING_CACHE_EXPIRY_SECONDS` (default **"25"** seconds)

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

---

[fastapi]: https://fastapi.tiangolo.com
[memcached]: https://memcached.org
