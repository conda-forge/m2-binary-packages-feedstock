mkdir $PREFIX/Library
cp -R $SRC_DIR/binary-${PKG_NAME}/* $PREFIX/Library/

rm -f $PREFIX/Library/.INSTALL
rm -f $PREFIX/Library/.BUILDINFO
rm -f $PREFIX/Library/.MTREE
rm -f $PREFIX/Library/.PKGINFO

if [[ "${PKG_NAME}" == "m2-file" ]]; then
  rm -rf $PREFIX/Library/usr/lib/python3.11/site-packages/__pycache__/
fi

if [[ "${PKG_NAME}" != "m2-msys2-launcher" && "${PKG_NAME}" != "m2-base" ]]; then
  test -d $PREFIX/Library/usr
fi

if [[ "${PKG_NAME}" == "m2-ca-certificates" ]]; then
  mkdir $PREFIX/Scripts
  cp $RECIPE_DIR/.m2-ca-certificates-post-link.bat $PREFIX/Scripts/
fi

if [[ "${PKG_NAME}" == "m2-filesystem" ]]; then
  echo "$PREFIX /conda_bin ntfs auto" >> ${PREFIX}/Library/etc/fstab
fi
