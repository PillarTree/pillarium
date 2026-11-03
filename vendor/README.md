# Vendored Python packages

Pillarium ships these pure Python packages inside the Debian package so
that the desktop environment installs on every distribution, even the
ones that do not carry `customtkinter` in their archive (Ubuntu 24.04
and Debian 13 removed it).

| Package | Version | License | Why |
| --- | --- | --- | --- |
| `customtkinter` | 6.0.0 | MIT | The user interface toolkit Pillarium is built with. |
| `darkdetect` | 0.8.0 | BSD-3-Clause | Dependency of customtkinter, it detects the light/dark mode of the system. |

Both directories are installed into `/usr/lib/python3/dist-packages` by
`build_deb.sh`.  A version installed with `pip` takes precedence over
the vendored one, because user site directories come first on the
Python path.

To refresh a vendored package:

```sh
pip download --no-deps --dest /tmp/wheels customtkinter==6.0.0 darkdetect==0.8.0
cd /tmp/wheels && unzip -q customtkinter-*.whl -d /tmp/x && rm -rf vendor/customtkinter
cp -r /tmp/x/customtkinter vendor/
```

The upstream projects are:

* <https://github.com/tomchen88/customtkinter>
* <https://github.com/albertosottile/darkdetect>
