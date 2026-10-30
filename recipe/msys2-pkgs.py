# Copyright 2023 Isuru Fernando
# SPDX-License-Identifier: BSD-3-Clause
#
# Yes, this script is horrible but since it works I do not intend to
# spend any time 'improving' it.

import hashlib
import tarfile
import re
import subprocess
import os
import shutil
from ordered_set import OrderedSet


date = "20261029"
snapshot_url = f"https://github.com/conda-forge/m2-binary-packages-feedstock/releases/download/{date}"
binary_index_url = snapshot_url + "/"
source_url = snapshot_url + "/"

to_process = OrderedSet([
        "git",
        "automake-wrapper",
        "make",
        "sed",
        "libtool",
        "autoconf-wrapper",
        "findutils",
        "m4",
        "bash",
        "texinfo",
        "p7zip",
        "curl",
        "base",
        "tar",
        "zip",
        "unzip",
        "diffutils",
        "patch",
        "patchutils",
        "texinfo-tex",
        "pkgconf",
        # autoconf is 2.71, we need 2.72 as well
        "autoconf2.72"
    ])

#to_process = OrderedSet([
#        "filesystem",
#    ])

provides = {
    "sh": "bash",
    "libuuid": "libutil-linux",
    "awk": "gawk",
    "perl-IO-stringy": "perl-IO-Stringy",
    "autoconf": "autoconf-wrapper",
    "pkg-config": "pkgconf",
}

license_text_to_spdx = {
    "GPL2": "GPL-2.0-or-later",
    "GPL": "GPL-3.0-or-later",
    "GPL3": "GPL-3.0-or-later",
    "LGPL": "LGPL-3.0-or-later", 
    "LGPL3": "LGPL-3.0-or-later",
    "BSD": "BSD-3-Clause",
    "custom:BSD": "BSD-3-Clause",
    "custom:unRAR": "LicenseRef-unRAR",
    "BSD-2-Clause": "BSD-2-Clause",
    "MIT": "MIT",
    "custom": "LicenseRef-CustomLicense",
    "PublicDomain": "LicenseRef-Public-Domain",
    "MPL": "MPL-2.0",
    "PerlArtistic": "Artistic-1.0-Perl",
}

seen = {}


def get_pkgs():
    os.makedirs("cache", exist_ok=True)
    os.makedirs("src-cache", exist_ok=True)
    database = f"src-cache/msys-{date}.db"
    if not os.path.exists(database):
        subprocess.check_call(["wget", snapshot_url + f"/msys-{date}.db", "-O", database + ".part"])
        os.replace(database + ".part", database)
    packages = {}
    checksums = {}
    # The directory also contains obsolete versions; use the repository's selected packages.
    with tarfile.open(database) as archive:
        for member in archive:
            if not member.name.endswith("/desc"):
                continue
            fields = dict(
                field.split("\n", 1)
                for field in archive.extractfile(member).read().decode().strip().split("\n\n")
            )
            name = fields["%NAME%"]
            filename = fields["%FILENAME%"]
            assert name not in packages and filename.startswith(name + "-")
            packages[name] = filename[len(name) + 1:]
            checksums[name] = fields["%SHA256SUM%"]
    assert packages and all(len(checksum) == 64 for checksum in checksums.values())
    return packages, checksums


pkg_latest_ver, pkg_checksums = get_pkgs()
# Refresh existing outputs even when they are no longer in the root packages' dependency closure.
package_names = {name.lower(): name for name in pkg_latest_ver}
with open("recipe/recipe.yaml") as f:
    for name in sorted(set(re.findall(r"      name: m2-(.+)", f.read()))):
        if name in {"autoconf", "pkg-config", "perl-io-socket-ip"}:
            continue  # Replaced upstream; compatibility outputs are emitted below.
        to_process.add(package_names[name])


def get_info(pkginfo, desc):
    return [
        line[len(f"{desc} = ") :].strip()
        for line in pkginfo
        if line.startswith(f"{desc} = ")
    ]

def as_spdx(license_text):
    if license_text.startswith("spdx:"):
        return license_text[5:].replace("AND GCC-exception", "WITH GCC-exception")
    
    if license_text in license_text_to_spdx:
        return license_text_to_spdx[license_text]

    assert False, f"Unknown license {license_text}"


def get_depends(pkg):
    # download and extract binary
    info = pkg_latest_ver[pkg]
    basename = f"cache/{pkg}-{info}"
    url = f"{binary_index_url}/{pkg}-{info}"
    if not os.path.exists(basename):
        if "github" in url:
            url = url.replace("~", ".")
        subprocess.check_call(["wget", url, "-O", basename + ".part"])
        os.replace(basename + ".part", basename)
    with open(basename, "rb") as f:
        assert hashlib.file_digest(f, "sha256").hexdigest() == pkg_checksums[pkg], basename
    pkginfo = subprocess.check_output(["bsdtar", "-xOf", basename, ".PKGINFO"]).decode().splitlines()

    # download source
    pkgbases = get_info(pkginfo, "pkgbase")
    pkgbase = pkgbases[0] if pkgbases else pkg
    pkgver = get_info(pkginfo, "pkgver")[0]
    src1 = f"{source_url}/{pkgbase}-{pkgver}.src.tar.zst"
    src2 = f"{source_url}/{pkgbase}-{pkgver}.src.tar.gz"
    if not os.path.exists("src-cache/" + os.path.basename(src1)) and not os.path.exists(
        "src-cache/" + os.path.basename(src2)
    ):
        try:
            src_name = src1
            subprocess.check_call(
                [
                    "wget",
                    src1.replace("~", ".") if "github" in source_url else src1,
                    "-O",
                    "src-cache/" + os.path.basename(src1),
                ]
            )
        except subprocess.CalledProcessError:
            os.remove("src-cache/" + os.path.basename(src1))
            try:
                src_name = src2
                subprocess.check_call(
                    [
                        "wget",
                        src2.replace("~", ".") if "github" in source_url else src2,
                        "-O",
                        "src-cache/" + os.path.basename(src2),
                    ]
                )
            except subprocess.CalledProcessError:
                os.remove("src-cache/" + os.path.basename(src2))
                src_name = None
    elif os.path.exists("src-cache/" + os.path.basename(src1)):
        src_name = src1
    elif os.path.exists("src-cache/" + os.path.basename(src2)):
        src_name = src2
    else:
        src_name = None

    # get dependencies
    depends = get_info(pkginfo, "depend")
    depends = [dep for dep in depends if not dep.startswith("pacman")]
    if pkg == "bash":
        # make sure bash comes with the bashrc files
        depends.append("filesystem")
    spdx = " AND ".join(as_spdx(license) for license in get_info(pkginfo, "license"))
    spdx = re.sub(r" AND ([\w.-]+-exception-[\d.]+)", r" WITH \1", spdx)
    desc = get_info(pkginfo, "pkgdesc")[0]
    url = get_info(pkginfo, "url")[0] or f"https://packages.msys2.org/package/{pkg}"
    return depends, spdx, desc, url, src_name


while to_process:
    pkg = to_process.pop()
    depends, spdx, desc, url, src_name = get_depends(pkg)
    for i, full_dep in enumerate(depends):
        dep = full_dep.split(">")[0].split("=")[0].split("<")[0]
        cond = full_dep[len(dep) :]
        dep = provides.get(dep, dep)
        dep = package_names.get(dep.lower(), dep)
        if cond:
            depends[i] = f"{dep} {cond.replace('~', '!')}"
        else:
            depends[i] = dep
        if dep == "perl-io-socket-ip":
            if "perl" not in seen:
                to_process.add("perl")
        elif dep not in seen:
            to_process.add(dep)
    seen[pkg] = depends, spdx, desc, url, src_name


meta = f"""recipe:
  name: m2-binary-packages
  version: "{date}"
"""

sources_template = """
      - url:
            - https://repo.msys2.org/msys/{{ msys_type }}/{{ url_base }}
            - {{ snapshot_url }}/{{ snapshot_basename }}
        sha256: {{ sha256 }}
        target_directory: {{ type }}-{{ name }}{{ patches }}
"""

meta += """
build:
  number: 11
  noarch: generic
  dynamic_linking:
    overlinking_behavior: ignore

outputs:"""

output_template = """
  - package:
      name: m2-{{ name }}
      version: "{{ version }}"
    source:
{{ sources }}
    build:
      noarch: generic
      script:
        file: ${{ "install_pkg.bat" if build_platform in ["win-64", "win-arm64"] else "install_pkg.sh" }}{{ prefix_detection }}
    requirements:
      host:
{{ host_depends }}
      run:
{{ run_depends }}{{ tests }}
    about:
      homepage: {{ url }}
      license: {{ license }}
      summary: |
        {{ summary }}
"""


dep_map = {}
smoke_tests = {
    "bash": ['bash --noprofile --norc -c "exit 0"'],
    "make": ["make --version"],
    "git": ["git --version"],
    "curl": ["curl --version"],
    "autoconf-wrapper": ['bash -c "autoconf --version"'],
    "pkgconf": ["pkg-config --version"],
    "perl": ['perl -MIO::Socket::IP -e "print $IO::Socket::IP::VERSION"'],
    "brotli": [
        "brotli --version",
        "echo MSYS2 snapshot round trip > original.txt",
        "brotli --output=compressed.br original.txt",
        "brotli --decompress --output=roundtrip.txt compressed.br",
        "fc /b original.txt roundtrip.txt",
    ],
}

for pkg, (depends, spdx, desc, url, src_url) in seen.items():
    print(f"{pkg} {pkg_latest_ver[pkg]} {' '.join(depends)}")
    filename = pkg_latest_ver[pkg]

    sources = []
    for t in ["binary-m2", "source"]:
        if t == "source" and not src_url:
            continue

        if t == "source":
            sha256 = (
                subprocess.check_output(
                    ["sha256sum", "src-cache/" + os.path.basename(src_url)]
                )
                .decode("utf-8")
                .split(" ")[0]
            )
            msys_type = "sources"
            url_base = os.path.basename(src_url)
        else:
            sha256 = (
                subprocess.check_output(["sha256sum", f"cache/{pkg}-{filename}"])
                .decode("utf-8")
                .split(" ")[0]
            )
            msys_type = "x86_64"
            url_base = f"{pkg}-{filename}"

        patches = ""
        if t == "binary-m2" and pkg.lower() == "filesystem":
            patches = """
        patches:
          - patches/filesystem/0001-Remove-etc-post-install-07-pacman-key-post.patch
          - patches/filesystem/0002-Use-Windows-users-temporary-directory-as-tmp.patch
            """.rstrip()

        source_info = {
            "name": pkg.lower(),
            "tarname": f"{pkg}-{filename}",
            "url_base": url_base,
            "snapshot_basename": url_base.replace("~", "."),
            "sha256": sha256,
            "type": t,
            "msys_type": msys_type,
            "patches": patches,
            "date": date,
            "snapshot_url": snapshot_url,
        }

        text = sources_template.strip("\n")
        for k, v in source_info.items():
            text = text.replace(f"{{{{ {k} }}}}", v)
        sources.append(text)

    if pkg.lower() != "msys2-runtime":
        depends += ["msys2-runtime"]
    dep_map[pkg] = depends

    host_depends = depends.copy()
    host_depends += [f"conda-epoch ={date}"]

    prefix_detection = ""
    if pkg.lower() == "filesystem":
      prefix_detection = """
      prefix_detection:
        force_file_type:
          text:
            - Library/etc/fstab"""

    tests = ""
    if pkg != "base":
        tests = '\n    tests:\n      - package_contents:\n          files:\n            - "Library/**"'
    else:
        tests = '\n    tests:\n      - script:\n          - echo "MSYS2 base dependencies installed"'
    if pkg in smoke_tests:
        tests += '\n      - script:\n          - set "PATH=%PREFIX%\\Library\\usr\\bin;%PATH%"'
        tests += "".join("\n          - " + command for command in smoke_tests[pkg])

    info = {
        "name": pkg.lower(),
        "version": ".".join(filename.split("-")[:2]).replace("~", "!"),
        "run_depends": "\n".join(f"        - m2-{dep.lower()}" for dep in depends),
        "host_depends": "\n".join(f"        - m2-{dep.lower()}" for dep in host_depends),
        "license": spdx,
        "summary": desc,
        "url": url,
        "sources": "\n".join(sources),
        "prefix_detection": prefix_detection,
        "tests": tests,
    }
    
    text = output_template
    for k, v in info.items():
        text = text.replace(f"{{{{ {k} }}}}", v)
    meta += text

    

# Keep conda package names that MSYS2 replaced or folded into another package.
for name, version, replacement in [
    ("autoconf", "2.73.1", "autoconf-wrapper"),
    ("pkg-config", "3.0.10.1", "pkgconf"),
    ("perl-io-socket-ip", "0.43", "perl"),
]:
    meta += f"""
  - package:
      name: m2-{name}
      version: "{version}"
    requirements:
      host:
        - m2-conda-epoch ={date}
      run:
        - m2-{replacement}
    tests:
      - script:
          - echo "m2-{name} is provided by m2-{replacement}"
    about:
      homepage: https://www.msys2.org
      license: BSD-3-Clause
      license_file: recipe-scripts-license.txt
      summary: Compatibility package for m2-{replacement}
"""

meta += """
about:
  homepage: https://github.com/conda-forge/m2-binary-packages-feedstock
  license: BSD-3-Clause
  license_file: recipe-scripts-license.txt
  summary: Repackaged msys2 x86_64 binaries

extra:
  recipe-maintainers:
    - isuruf
"""

recipe_dir = (
    "recipes/m2-recipes"
    if os.path.exists(os.path.join("recipes", "m2-recipes"))
    else "recipe"
)

output_names = set(re.findall(r"      name: (.+)", meta))
assert len(output_names) == len(seen) + 3
for dependencies in dep_map.values():
    for dependency in dependencies:
        assert "m2-" + dependency.lower().split()[0] in output_names, dependency
assert all(info[4] for info in seen.values()), "Every binary must have a source archive"
assert 'version: "1.2.1.1"' in meta and "skip: true" not in meta

with open(os.path.join(recipe_dir, "recipe.yaml"), "w") as f:
    f.write(meta)
