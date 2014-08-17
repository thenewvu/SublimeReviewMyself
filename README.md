## Introduction

__An in-source todo manage plugin for Subline Text 3, list todos in your sources, help you always know what should do next.__

## Screenshots

![Review Myself Result](http://i.imgur.com/55Wnh67.png "Review Myself - Result")

## Setup

By default, Review Myself has this default settings:

	{
		"todo_patterns": [
			"TODO\\s*:+\\s*(?P<todo>.*)$"
		],
		"priority_patterns": [
			"#p(?P<priority>[1-3])"
		],
		"is_ignore_case": true,
		"ignored_dir_patterns": [".svn", ".git", ".hg", "CVS"],
		"only_care_file_patterns": ["*.cpp", "*.c", "*.h", "*.py", "*.js", "*.md"],
		"color_scheme": "Packages/Review Myself/ReviewMyself-NeonDark.hidden-tmTheme"
	}

To tweak them, go to Preferences -> Package Settings -> Review Myself -> Settings - User, ST will open a __user setting file__ for you, put your settings there and save it.

## How to take a todo ?

Simple as this:

    TODO: the highest priority todo, should be done right now #p1
	TODO: when p1 todos are clear, this will be a p1 #p2
	TODO: another p1 candidate todo #p2
	TODO: take a look in the tomorrow morning, it's ok :D #p3

By default, ReviewMyself only supports priority number from 1 to 3. I don't think we need more than that, but you can customize it (just increment the number in the priority pattern).

## How list todos ?

To list todos in the current file:

	Ctrl + Shift + P, then enter command: ReviewMyself: Current File

To list todos in a file or a folder in side bar:

	Right click on the file or the folder => choose ReviewMyself

To list todos in the current Sublime Text project:

 	Ctrl + Shift + P, then enter command: ReviewMyself: Folders in Project

## Tweak the color scheme

Download [the default color scheme file](https://github.com/thenewvu/SublimeReviewMyself/blob/master/ReviewMyself-NeonDark.hidden-tmTheme).

Tweak then put it in your User folder. [Color Highlighter](https://sublime.wbond.net/packages/Color%20Highlighter) will help you tweak color easily.

Add this line to your Review Myself user setting file (Preferences -> Package Settings -> Review Myself -> Settings - User):

	{
		"color_scheme": "Packages/User/ReviewMyself-NeonDark.hidden-tmTheme"
	}

## Get involved ?

If have any issue, please post here: https://github.com/thenewvu/SublimeReviewMyself/issues

If you want to fork or contribute: https://github.com/thenewvu/SublimeReviewMyself/

If you want to buy some coffee for me: https://www.gittip.com/thenewvu/

## References

- This is a fork from [TodoReview](https://sublime.wbond.net/packages/TodoReview) by [jonathandelgado](https://sublime.wbond.net/browse/authors/jonathandelgado).
- GetBasenameFromPath function come from http://stackoverflow.com/questions/8384737/python-extract-file-name-from-path-no-matter-what-the-os-path-format
- Color scheme is based on [Theme - Farzher](https://sublime.wbond.net/packages/Theme%20-%20Farzher) by [farzher](https://sublime.wbond.net/browse/authors/farzher)
- Many other sources

## Licenses

[The MIT License (MIT)](https://github.com/thenewvu/SublimeReviewMyself/blob/master/LICENSE)
