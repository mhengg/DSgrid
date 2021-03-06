# dsgrid-legacy-efs-api Developer Readme

## Developer Dependencies

**pip extras**

```
pip install -e .[dev,ntbks]
```

**Additional software required for publishing documentation:**

- [Pandoc](https://pandoc.org/installing.html)

## Publish Documentation

The documentation is built with [Sphinx](http://sphinx-doc.org/index.html). There are several steps to creating and publishing the documentation:

1. Convert .md input files to .rst
2. Refresh API documentation
3. Build the HTML docs
4. Push to GitHub

### Markdown to reStructuredText

Markdown files are registered in `docs/md_files.txt`. Paths in that file should be relative to the docs folder and should exclude the file extension. For every file listed there, the `dev/md_to_rst.py` utility will expect to find a markdown (`.md`) file, and will look for an optional `.postfix` file, which is expected to contain `.rst` code to be appended to the `.rst` file created by converting the input `.md` file. Thus, running `dev/md_to_rst.py` on the `docs/md_files.txt` file will create revised `.rst` files, one for each entry listed in the registry. In summary:

```
cd docs
python ../dev/md_to_rst.py source/md_files.txt
```

### Refresh API Documentation

- Make sure dsgrid-legacy-efs-api is installed or is in your PYTHONPATH
- Delete the contents of `source/api`.
- Run `sphinx-apidoc -o source/api ../dsgrid` from the `docs` folder.
- 'git push' changes to the documentation source code as needed.
- Make the documentation per below

### Building HTML Docs

Run `make html` for Mac and Linux; `make.bat html` for Windows.

### Pushing to GitHub Pages

#### Mac/Linux

```cd .
make github
```

#### Windows

```
make.bat html
```

Then run the github-related commands by hand:

```
git branch -D gh-pages
git push origin --delete gh-pages
ghp-import -n -b gh-pages -m "Update documentation" .\_build\html
git checkout gh-pages
git push origin gh-pages
git checkout main # or whatever branch you were on
```

## Release on pypi

1. [using testpyi](https://packaging.python.org/guides/using-testpypi/) has good instructions for setting up your user account on TestPyPI and PyPI, and configuring twine to know how to access both repositories.
   
2. Make sure you have packaging dependencies

    ```
    pip install setuptools wheel twine
    ```
   
3. Test the package

    ```
    python setup.py sdist bdist_wheel
    twine check dist/*
    twine upload --repository testpypi dist/*
    # look at https://test.pypi.org/project/dsgrid-legacy-efs-api/
    pip install --index-url https://test.pypi.org/simple/ dsgrid-legacy-efs-api[ntbks]
    # check it out ... fix things ...
    ```

4. Upload to pypi
   
   ```
   twine upload --repository pypi dist/*
   ```
