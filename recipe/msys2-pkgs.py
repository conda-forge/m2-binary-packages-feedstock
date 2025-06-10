# Copyright 2023 Isuru Fernando
# SPDX-License-Identifier: BSD-3-Clause
#
# Yes, this script is horrible but since it works I do not intend to
# spend any time 'improving' it.

from bs4 import BeautifulSoup
import requests
import subprocess
import os
import shutil
from ordered_set import OrderedSet


date = "20250515"
binary_index_url = (
    #"https://repo.msys2.org/msys/x86_64/"
    f"https://github.com/conda-forge/m2-binary-packages-feedstock/releases/download/{date}/"
)
source_url = (
    #"https://repo.msys2.org/msys/sources/"
    f"https://github.com/conda-forge/m2-binary-packages-feedstock/releases/download/{date}/"
)

to_process = OrderedSet([
        "git",
        "automake-wrapper",
        "make",
        "sed",
        "libtool",
        "autoconf",
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
        "pkg-config",
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
}

license_text_to_spdx = {
    "GPL2": "GPL-2.0-or-later",
    "GPL": "GPL-3.0-or-later",
    "GPL3": "GPL-3.0-or-later",
    "LGPL": "LGPL-3.0-or-later", 
    "LGPL3": "LGPL-3.0-or-later",
    "BSD": "BSD-3-Clause",
    "custom:BSD": "BSD-3-Clause",
    "BSD-2-Clause": "BSD-2-Clause",
    "MIT": "MIT",
    "custom": "LicenseRef-CustomLicense",
    "PublicDomain": "LicenseRef-Public-Domain",
    "MPL": "MPL-2.0",
    "PerlArtistic": "Artistic-1.0-Perl",
}

seen = {}


def get_pkgs():
    if not os.path.exists("src-cache/index.html"):
        if "github" in binary_index_url:
            url = binary_index_url + "index.html"
        else:
            url = binary_index_url
        subprocess.check_call(["wget", url, "-O", "src-cache/index.html"])
    with open("src-cache/index.html") as f:
        s = BeautifulSoup(f.read(), "html.parser")
    full_names = [
        node.get("href")
        for node in s.find_all("a")
        if node.get("href").endswith((".tar.zst", "tar.xz"))
    ]

    def get_name_ver(pkg):
        b = os.path.basename(pkg)
        return ("-".join(b.split("-")[:-3]), "-".join(b.split("-")[-3:]))

    # format: msy2-w32api-headers-10.0.0.r16.g49a56d453-1-x86_64.pkg.tar.zst
    return list(sorted([get_name_ver(pkg) for pkg in full_names]))


pkg_latest_ver = dict(get_pkgs())
print(pkg_latest_ver)


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
            subprocess.check_call(["wget", url.replace("~", "."), "-O", basename])
        else:
            subprocess.check_call(["wget", url, "-O", basename])
    subprocess.check_call(["mkdir", "-p", "cache/tmp"])
    subprocess.check_call(["bsdtar", "-xf", basename, "--directory=cache/tmp"])
    with open("cache/tmp/.PKGINFO") as f:
        pkginfo = f.readlines()

    # download source
    pkgbases = get_info(pkginfo, "pkgbase")
    pkgbase = pkgbases[0] if pkgbases else pkg
    pkgver = get_info(pkginfo, "pkgver")[0]
    src1 = f"{source_url}/{pkgbase}-{pkgver}.src.tar.zst"
    src2 = f"{source_url}/{pkgbase}-{pkgver}.src.tar.gz"
    if "github" in source_url:
        src1 = src1.replace("~", ".")
        src2 = src2.replace("~", ".")
    if not os.path.exists("src-cache/" + os.path.basename(src1)) and not os.path.exists(
        "src-cache/" + os.path.basename(src2)
    ):
        try:
            src_name = src1
            subprocess.check_call(
                [
                    "wget",
                    src1,
                    "-O",
                    "src-cache/" + os.path.basename(src1),
                    "--no-check-certificate",
                ]
            )
        except subprocess.CalledProcessError:
            os.remove("src-cache/" + os.path.basename(src1))
            try:
                src_name = src2
                subprocess.check_call(
                    [
                        "wget",
                        src2,
                        "-O",
                        "src-cache/" + os.path.basename(src2),
                        "--no-check-certificate",
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
    elif pkg == "libiconv":
        # break a cycle
        depends.remove("libintl")
    license_text = get_info(pkginfo, "license")[0]
    spdx = as_spdx(license_text)
    desc = get_info(pkginfo, "pkgdesc")[0]
    url = get_info(pkginfo, "url")[0]
    return depends, spdx, desc, url, src_name


while to_process:
    pkg = to_process.pop()
    depends, spdx, desc, url, src_name = get_depends(pkg)
    for i, full_dep in enumerate(depends):
        dep = full_dep.split(">")[0].split("=")[0].split("<")[0]
        cond = full_dep[len(dep) :]
        dep = provides.get(dep, dep)
        if cond:
            depends[i] = f"{dep} {cond.replace('~', '!')}"
        else:
            depends[i] = dep
        if dep not in seen:
            to_process.add(dep)
    seen[pkg] = depends, spdx, desc, url, src_name


meta = f"""recipe:
  name: m2-binary-packages
  version: "{date}"
"""

sources_template = """
      - url:
            - https://repo.msys2.org/msys/{{ msys_type }}/{{ url_base }}
            - https://github.com/conda-forge/m2-binary-packages-feedstock/releases/download/{{ date }}/{{ url_base }}
        sha256: {{ sha256 }}
        target_directory: {{ type }}-{{ name }}{{ patches }}
"""

meta += """
build:
  number: 7
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
        file: ${{ "install_pkg.bat" if win else "install_pkg.sh" }}{{ prefix_detection }}
      skip: {{ skip }}
    requirements:
      host:
{{ host_depends }}
      run:
{{ run_depends }}
    about:
      homepage: {{ url }}
      license: {{ license }}
      summary: |
        {{ summary }}
"""


dep_map = {}

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
            "url_base": url_base.replace("~", "."),
            "sha256": sha256,
            "type": t,
            "msys_type": msys_type,
            "patches": patches,
            "date": date,
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
            - etc/fstab"""

    skip = "false"

    if pkg.lower() != "filesystem":
        skip = "true"

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
        "skip": skip,
    }
    
    text = output_template
    for k, v in info.items():
        text = text.replace(f"{{{{ {k} }}}}", v)
    meta += text

    

# print(dep_map)

meta += """
about:
  homepage: https://github.com/conda-forge/m2-binary-packages-feedstock
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

with open(os.path.join(recipe_dir, "recipe.yaml"), "w") as f:
    f.write(meta)
