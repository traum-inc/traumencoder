# Traum Encoder

A simple ProRes batch encoder for production workflows, powered by the [ffmpeg tools](https://ffmpeg.org/).

![Screenshot](https://raw.githubusercontent.com/traum-inc/traumencoder/master/screenshot.png)

## Installation

First, download a binary for your platform from the [release page](https://github.com/traum-inc/traumencoder/releases/tag/v0.1-alpha). On Windows, unzip and run the .exe executable within the folder. On macOS, extract the app from the disk image and double-click to run.

## Instructions

The encoder accepts both video files and image sequences.

#### Importing media
You can add videos by dragging and dropping them into the central area, or by click 'Add Videos' and selecting them using the file browser.

To add image sequences, drag the containing folder into the central area, or click 'Add Folder' and select the containing folder.

Some points to be aware of:

* When folders are added, they are scanned *recursively*, and any contained media (videos or image sequences) will be added to the list.
* Image sequences will be imported with the frame rate selected in the drop-down box in the toolbar (default 30fps). So if you need to add sequences of different frame rates, make sure to select the rate before you add them to the list.

To stop a recursive scan, you can click 'Stop Scan'. But it's a little buggy at the moment so it may still get stuck on a huge folder tree (eg if you attempt to scan your entire disk) and require a forced quit.

#### Preview and edit items

One the media items appear in the list, you can see various metadata - duration, frame rate, dimensions, codec, colorspace etc. Double click on an item to preview the source media via [ffplay](https://ffmpeg.org/ffplay.html).

You can edit the list by selecting items and pressing the delete key to remove them.

#### Encoding

Finally, select the desired [ProRes profile](https://support.apple.com/en-gb/HT202410) from the drop-down in the toolbar.

Either select a subset of the items in the list (a single item, or a multiple selection of items), or don't select any items to encode the entire list.

Click the 'Encode' button to start the encoding process. You should see items queue up and begin to encode, one at a time (although ffmpeg will use all your CPU resources to encode each item).

Press 'Stop' at any time to cancel the encode.

#### Results

Videos and image sequences are encoded into ProRes .mov files in the folder they were found in, with a `_prores.mov` suffix.

You can preview the encoded file by double-clicking on an encoded item. Again, this uses ffplay to preview rather than any native player such as QuickTime.


## Building

First make sure you have a Python 3.7.3 environment at least. Create a new virtualenv and install the requirements:

```
$ git clone https://github.com/traum-inc/traumencoder.git
$ cd traumencoder
$ virtualenv -p /usr/bin/python3 venv
$ source venv/bin/activate
$ pip install -r requirements.txt
```

Next download [ffmpeg binaries for your platform](https://ffmpeg.zeranoe.com/builds/) and copy them into the `bin/' folder.

At this point you should be able to run the application from the terminal:

```
$ python traumenc
```

If that works, you can build a self-contained executable or app by installing PyInstaller, and then running the build script:

```
$ pip install PyInstaller
$ ./scripts/build.sh
```

This will either build a tarball or a disk image in the `dist/` folder.

### Windows

On Windows it's a similar process, but use the PowerShell build script:

```
PS> git clone https://github.com/traum-inc/traumencoder.git
PS> cd traumencoder
PS> virtualenv venv
PS> venv/Scripts/activate
PS> pip install -r requirements.txt
```

You'll need to install the development version of PyInstaller to run the build script.

```
PS> pip install https://github.com/pyinstaller/pyinstaller/archive/develop.tar.gz
PS> scripts/build.ps1
```

This will create a zip file in the `dist/` folder.
