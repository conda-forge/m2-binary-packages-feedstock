# MSYS2 snapshot refresh

This recipe repackages a coordinated MSYS2 x86_64 snapshot. Every output uses
`m2-conda-epoch =20261029`; do not mix individual current MSYS2 binaries into an
older epoch without checking runtime compatibility.

## Regenerate this snapshot

From the feedstock root:

```sh
pixi exec --spec 'python>=3.11' --spec ordered-set --spec wget \
  --spec coreutils --spec libarchive -- python recipe/msys2-pkgs.py
```

The generator downloads the frozen repository database and archives from the
snapshot release. It selects versions from that database (not directory sorting),
checks binary SHA256 hashes, retains existing output names, and verifies that the
runtime dependency graph is closed and every binary has a source archive.
`cache/` and `src-cache/` are local download caches, not recipe files.

The 20261029 archives, database and `SHA256SUMS` are staged at:
https://github.com/wolfv/m2-binary-packages-feedstock/releases/tag/20261029

The primary recipe URLs still point to MSYS2. The release is a fallback for
archives removed from its rolling repository. Maintainers can mirror the assets
to the upstream feedstock release, change `snapshot_url`, and regenerate.

## Prepare a later snapshot

1. Use fresh download caches. Update `date` and the shared build number in the
   generator (unchanged upstream versions must also be republished).
2. Save `https://repo.msys2.org/msys/x86_64/msys.db` as
   `src-cache/msys-<date>.db`. Temporarily use the live MSYS2 binary and source
   directories for `binary_index_url` and `source_url` during generation.
3. Review removed/renamed packages, virtual dependencies, licenses, and the
   compatibility outputs. Do not silently drop existing conda package names.
4. Archive all selected binaries, matching sources, and the database in a release.
   GitHub normalizes `~` to `.` in asset names. Point the generator back to that
   frozen release and regenerate; check that the recipe is reproducible.
5. Update and publish `m2-conda-epoch` first, then build the full binary snapshot.
   New output names may need conda-forge output registration. Do not recommend
   upgrading until the whole snapshot is available.

## Validation

On Windows, with the new epoch available:

```sh
rattler-build build -r recipe -m .ci_support/win_64_.yaml --keep-build
```

The recipe checks package contents and smoke-tests Bash, Make, Git, curl,
autoconf, pkg-config, Perl's IO::Socket::IP, and a Brotli round trip. Cross-target
repackaging on macOS/Linux can validate sources, patches, and dependency solving,
but requires `--test skip` and does not replace native Windows tests.
