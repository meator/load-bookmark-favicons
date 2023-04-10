<div align="center">
  <img src="title-image.png">
</div>

[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

# About
load-bookmark-favicon can be used to load favicons of all bookmarks of Chromium based web browsers. This is useful when bookmarks are imported
into a newly set up web browser.

It works for remote and local websites with pretty all common favicon formats. It efficiently reuses favicons that are already saved in the browser.

## Q&A

1. Why?

   Because Chromium doesn't provide any way to mass fetch favicons of bookmarks. Favicons are a great way to distinguish one bookmark from another.
   But when someone has to import bookmarks, their favicons do not get loaded. The only solution in this situation is to click on each bookmark
   one by one to load favicons. load-bookmark-favicon can do this automatically, efficiently and with a nice progress bar!
   
   This is also a small project I have used to get familiar with the Python programming language.

2. Is this safe?

   load-bookmark-favicons uses Chromium internals files to load favicons. This can (but hopefully shouldn't) introduce some problems. Here is a quote from the
   `README` file present in Chromium's configuration:

   > Chromium settings and storage represent user-selected preferences and information and MUST not be extracted, overwritten or modified except through
   Chromium defined APIs.

   load-bookmark-favicon has been heavily tested to avoid any errors when manipulating Chromium's internals. load-bookmark-favicon only accesses two files,
   the `Bookmarks` file and the `Favicons` file, it doesn't modify important internal files.

3. Is this "correct"?

   load-bookmark-favicon doesn't guarantee that favicons loaded by it will 100% match favicons Chromium would load when the bookmarks would be opened manually.
   But in the great majority of cases there wouldn't be a noticeable difference. To combat this problem, load-bookmark-favicon gives its
   favicons lower priority than normally loaded favicons. This means that when you open a bookmark manually, the browser will fetch website's favicon and overwrite
   the one fetched by load-bookmark-favicon.

4. Some icons are still missing! Why?

   Some websites block automated requests. You can run load-bookmark-favicons with `-v` or `-vv` to see what is happening.

# Dependencies
load-bookmark-favicon uses mostly modules from the Python Standard Library, but it has some external dependencies as well:
- [`requests`](https://requests.readthedocs.io/en/latest/)
- [`PIL`](https://pillow.readthedocs.io/en/stable/)
- [`CairoSVG`](https://cairosvg.org/)

# Usage
load-bookmark-favicons may yield many warnings. They should be (mostly) harmless. Sometimes a bookmarked website can not be reached or it doesn't have
a favicon. load-bookmark-favicons skips these bookmarks.

load-bookmark-favicons is fully interruptable. No damage to the `Favicons` file will be done upon termination, however all progress will be lost.

The browser must not be running when load-bookmark-favicons is running (load-bookmark-favicons detects this and aborts).

You first need to locate your profile directory of your browser. It should contain `Bookmarks` and `Favicons` file. 
## Linux (Chromium)

In Linux, you can find Chromium's profile directory here[^1]
```
~/.config/chromium/Default
```

You can backup the `Favicons` file (optional):
```sh
cp <profile dir>/Favicons <profile dir>/Favicons~
```

You can now use load-bookmark-favicons:
```sh
load-bookmark-favicons.py <profile dir>/Bookmarks <profile dir>/Favicons
```

You can see example usage here:

<a href="https://asciinema.org/a/577156?autoplay=1"><img src="https://asciinema.org/a/577156.png"/></a>

## Windows (Google Chrome)

Setting up dependencies can be tricky in Windows. You should have Python 3.x and pip installed. Install all [dependencies](#dependencies) through pip. CairoSVG requires Cairo to function. Installing Cairo on Windows is surprisingly difficult. The simplest way (that I have tested) to install
it is to locate it in other program's files (Cairo is a part of GIMP and Inkscape for example), add it to [PATH](https://stackoverflow.com/questions/44272416/how-to-add-a-folder-to-path-environment-variable-in-windows-10-with-screensho) (if you have GIMP installed
you can add `C:\Program Files\GIMP 2\bin\` to path).

In Windows, profile directory is (usually) located here
```
%APPDATA%\..\Local\Google\Chrome\User Data\Default
```

You can copy the `Favicons` file somewhere to make a backup (optional).

You can now use load-bookmark-favicons[^2]:
```sh
py -m load-bookmark-favicons <profile dir>\Bookmarks <profile dir>\Favicons
```

# Testing
load-bookmark-favicons has been tested on both Linux and Windows using recent releases of Chromium and Google Chrome.

# Code style
This project uses the Black code formatter. This project abides to the [Google Python Style Guide](https://google.github.io/styleguide/pyguide.html).

# Reporting bugs
If you happen to find any bugs, please [report them](https://github.com/meator/load-bookmark-favicons/issues/new).

This project includes a special tool [check_database.py](check_database.py) that can be used to verify the integrity of the `Favicons` file.
If load-bookmark-favicons didn't crash but somehow corrupt the `Favicons` file or if it has damaged it in some other way, try running check_database.py
on the `Favicons` file and attach its output to the issue.

# TODO
- [ ] add Firefox support
- [ ] add support for data URLs
- [ ] implement mime sniffing in get_favicon_url
- [ ] improve best icon selection

[^1]: Various distributions and package managers can place configuration files in a different directory. If that is the case, you will have to find
the profile directory yourself.
[^2]: The exact method of script execution depends on how your Python is set up.
