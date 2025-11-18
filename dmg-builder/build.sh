#!/bin/zsh


# ---------------------------------------------------------------------
#                      Once per machine project
#
# # Store credentials (for later submission, once per machine)
# xcrun notarytool store-credentials "$KEYCHAIN_PROFILE" --apple-id "$APPLE_ID" --team-id "$TEAM_ID" --password "$APP_SPECIFIC"
#
# # Install a tool for creating a DMG
# brew install create-dmg
#
# # Create an icns for an application (after scaling logo to all image sizes)
# iconutil -c icns icon.iconset
#
# ---------------------------------------------------------------------


# ---------------------------------------------------------------------
#                      Set up your own config.sh
# 
# Read in the TEAM_ID
# echo "Generate a certificate by requesting a new authorized cert from KeychainAccess app on local machine."
# echo ""
# echo "Pick a 'Developer ID Application' and upload the locally generated request here:"
# echo "  https://developer.apple.com/account/resources/certificates/list"
# echo ""
# echo "Then enter the 10-character team ID alphanumeric string."
# read TEAM_ID
# TEAM_ID="${TEAM_ID:-ABCDE12345}"
# # App specific passwords can be generated at:
# #  https://account.apple.com/account/manage
# APP_SPECIFIC="abcd-efgh-ijkl-mnop"
# # Your developer Apple ID email
# APPLE_ID="your.email@domain.com"
# # Developer name and team ID comes from developer certificate
# DEV_NAME="Your Name"
# # Signature should look like this for a "Developer ID Application"
# SIGNATURE="Developer ID Application: $DEV_NAME ($TEAM_ID)"
# # Profile name is arbitrary
# KEYCHAIN_PROFILE="macos-2025"
# # The name of the app
# APP_NAME="macos-grok-overlay"
# 
# ---------------------------------------------------------------------

source config.sh

# Create a build environment
touch temp.egg-info
rm -rf env dist build *.egg-info
python3 -m venv env
source env/bin/activate
python3 -m pip install --upgrade pip
python3 -m pip install setuptools==70.3.0 py2app pyobjc
# Get the build directory name (containing this file).
#  - ${0} → The path to the script.
#  - :a → Resolves to an absolute path.
#  - :h → Extracts the directory portion.
#  - :t → Extracts the last component (i.e., the basename of the directory).
build_dir_name=${0:a:h:t}
# Build the '.app' with 'py2app'
pushd ..
python setup.py py2app --dist-dir="$build_dir_name"/dist --bdist-base="$build_dir_name"/build
popd
# Deactivate the python building environment
deactivate

# Codesign all the '.so' files within the app
find dist/$APP_NAME.app -type f -name "*.so" -exec codesign --deep --force --verify --verbose --options runtime --timestamp --sign "$SIGNATURE" {} \;
# Codesign the app itself
codesign --deep --force --verify --verbose --options runtime --timestamp --sign "$SIGNATURE" dist/$APP_NAME.app
# Create a ZIP for notary submission
ditto -c -k --keepParent dist/$APP_NAME.app $APP_NAME.zip
# Submit for notarization
xcrun notarytool submit $APP_NAME.zip --keychain-profile "$KEYCHAIN_PROFILE" --wait

# # Check the log from notarization
# xcrun notarytool log $NOTARIZATION_ID --keychain-profile "$KEYCHAIN_PROFILE" | less

# Check permissions to make sure it's valid
spctl -a -vvv -t exec dist/$APP_NAME.app
# Staple the permissions to the .app
xcrun stapler staple dist/$APP_NAME.app
# Create a DMG that provides an easy-installer
create-dmg --volname "$APP_NAME" --window-size 600 300 --icon-size 100 --app-drop-link 400 150 $APP_NAME.dmg dist/$APP_NAME.app
