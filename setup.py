# Try to import setuptools (if it fails, the user needs that package)
try: 
    from setuptools import setup
except:
    # Custom error (in case user does not have setuptools)
    class DependencyError(Exception): pass
    raise(DependencyError("Missing python package 'setuptools'.\n  pip install --user setuptools"))

import os
import sys

# Convenience function for reading information files
def read(f_name, empty_lines=False):
    text = []
    with open(os.path.join(package_about, f_name)) as f:
        for line in f:
            line = line.strip("\n")
            if (not empty_lines) and (len(line.strip()) == 0): continue
            if (len(line) > 0) and (line[0] == "%"): continue
            text.append(line)
    return text

# Go to the "about" directory in the package directory.
source_page = "grok"
package_name = f"macos-{source_page}-overlay"
package_about = os.path.join(os.path.dirname(os.path.abspath(__file__)), package_name.replace("-","_"), "about")

if __name__ == "__main__":
    #      Read in the package description files     
    # ===============================================
    package = package_name.replace("-", "_")
    version =read("version.txt")[0]
    description = read("description.txt")[0]
    keywords = read("keywords.txt")
    classifiers = read("classifiers.txt")
    name, email, git_username = read("author.txt")
    requirements = read("requirements.txt")
    # Call "setup" to formally set up this module.
    if 'py2app' not in sys.argv:
        setup(
            author = name,
            author_email = email,
            name=package,
            packages=[package],
            package_data={
                package: [f"logo/logo_white.png", f"logo/logo_black.png"],
            },
            entry_points={
                "console_scripts": [
                    f"macos-{source_page}-overlay = macos_{source_page}_overlay:main",
                ],
            },
            include_package_data=True,
            install_requires=requirements,
            version=version,
            url = 'https://github.com/{git_username}/{package}'.format(
                git_username=git_username, package=package),
            download_url = 'https://github.com/{git_username}/{package}/archive/{version}.tar.gz'.format(
                git_username=git_username, package=package, version=version),
            description = description,
            # scripts=[os.path.join(package,"setup.py")],
            keywords = keywords,
            python_requires = '>=3.10',
            license='MIT',
            classifiers=classifiers
        )
    elif 'py2app' in sys.argv:
        setup(
            app=[f'run.py'],  # Entry point to your application
            options={
                'py2app': {
                    'iconfile': f'{package}/logo/icon.icns',  # Path to your app icon
                    'plist': {
                        'CFBundleName': package_name,
                        'CFBundleIdentifier': f'com.github-{git_username}.macos{source_page}ovelay',  # Unique identifier
                        'LSUIElement': True,  # Hide from Dock and Cmd+Tab
                    },
                    'includes': ['pyobjc'],  # Ensure required dependencies are bundled
                    'packages': [package],
                    'resources': [
                        f"{package}/logo/logo_white.png",
                        f"{package}/logo/logo_black.png"
                    ],
                }
            },
            setup_requires=['py2app'],
        )
