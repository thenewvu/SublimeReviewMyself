# This is a fork of TodoReview by @jonathandelgado.
# Also thanks to @robcowie and @dnatag, who developed SublimeTODO, which TodoReview forked from.

import sublime_plugin
import sublime
import os
import threading
import fnmatch
import re
import timeit
import ntpath


class Util():
	@staticmethod
	def log(tag, message):
		print("{tag}: {message}".format(tag = tag, message = message))

	@staticmethod
	def status(message):
		sublime.status_message("{message}".format(message = message))

	@staticmethod
	def isMatchUnixPatterns(text, patterns):
		for pattern in patterns:
			if fnmatch.fnmatch(text, pattern):
				return True
		return False

	@staticmethod
	def filterByUnixPatterns(texts, patterns, keep_if_match):
		filtered_texts = []
		for text in texts:
			if keep_if_match == Util.isMatchUnixPatterns(text, patterns):
				filtered_texts.append(text)

		return filtered_texts

	'''
		Extract directory/file name from a path.
		Ex:
		Inputs:		'a/b/c/', 'a/b/c', '\\a\\b\\c', '\\a\\b\\c\\', 'a\\b\\c', 'a/b/../../a/b/c/', 'a/b/../../a/b/c'
		Outputs:	'c', 'c', 'c', 'c', 'c', 'c', 'c'
		Ref: http://stackoverflow.com/questions/8384737/python-extract-file-name-from-path-no-matter-what-the-os-path-format
	'''
	@staticmethod
	def getBasenameFromPath(path):
		head, tail = ntpath.split(path)
		return tail or ntpath.basename(head)

class Settings():
	def __init__(self, view, setting_name):
		self.default = sublime.load_settings("{setting_name}.sublime-settings".format(setting_name = setting_name))
		self.user = view.settings().get("{setting_name}".format(setting_name = setting_name), {})

	def get(self, fieldName, defaultValue):
		return self.user.get(fieldName, self.default.get(fieldName, defaultValue))

class TodoSearchEngine():
	TAG = "ReviewMyself.TodoSearchEngine"

	def __init__(self):
		self.paths_to_search = []
		self.todo_filter = None
		self.priority_filter = None
		self.ignored_dir_patterns = []
		self.only_care_file_patterns = []
		self.counter = Counter()

	def hasIgnoredDirs(self):
		return len(self.ignored_dir_patterns) > 0

	def hasOnlyCareFiles(self):
		return len(self.only_care_file_patterns) > 0

	'''
	pseudocode:
		each path in paths:
			check exists
			if is file path:
				yeild it
			else
				if has only care files:
					only keep those files

				if has ignored dirs:
					remove ignored dirs

				yeild rest of files
	'''
	def walk(self):
		for path_to_search in self.paths_to_search:
			path_to_search = os.path.realpath(os.path.expanduser(os.path.abspath(path_to_search)))
			
			if os.path.exists(path_to_search):
				if os.path.isfile(path_to_search):
					yield path_to_search # if user indicated a file, that mean he/she want to scan that file, so just yield it
				
				for dirpath, dirnames, filenames in os.walk(path_to_search, topdown = True):
					if self.hasOnlyCareFiles():
						filenames[:] = Util.filterByUnixPatterns(texts = filenames, patterns = self.only_care_file_patterns, keep_if_match = True)

					if self.hasIgnoredDirs():
						dirnames[:] = Util.filterByUnixPatterns(texts = dirnames, patterns = self.ignored_dir_patterns, keep_if_match = False)

					for filename in filenames:
						filepath = os.path.join(dirpath, filename)
						yield filepath

	def search(self):
		for filepath in self.walk():
			try:
				file_stream = open(filepath, 'r', encoding='utf-8')
				for linenum, line in enumerate(file_stream, 1):
					match = self.todo_filter.search(line)
					if match:
						match_groups = match.groupdict()

						todo = ""
						if "todo" in match_groups:
							todo = str(match_groups["todo"]).strip()

						if todo:
							match = self.priority_filter.search(todo)

							priority = 9999 #TODO: unhardcode max priority #p3
							if match:
								match_groups = match.groupdict()
								if "priority" in match_groups:
									priority = int(match_groups["priority"])
									todo = todo.replace(match.group(0), "")

							yield {
								'filepath': filepath,
								'linenum': linenum,
								'todo': todo,
								'priority': priority
							}

			except Exception as e:
				file_stream = None
				Util.log(TodoSearchEngine.TAG, r"Can't read '{filepath}', error: {exception_info}".format(
					filepath = filepath,
					exception_info = e))
				
			finally:
				self.counter.increment()
				if file_stream is not None:
					file_stream.close()

class ResultView():
	@staticmethod
	def get():
		active_window = sublime.active_window()
		for view in active_window.views():
			if ResultView.isResultView(view):
				return view

		result_view = active_window.new_file()
		result_view.set_name('ReviewMyself')
		result_view.set_scratch(True)
		result_view.settings().set('review_myself_view', True)
		result_view.settings().set('command_mode', True)
		result_view.settings().set('word_wrap', False)
		result_view.settings().set("line_numbers", False)
		settings = Settings(result_view, "ReviewMyself")
		result_view.settings().set("color_scheme", settings.get("color_scheme", ""))
		result_view.assign_syntax(r"Packages/Review Myself/ReviewMyself.tmLanguage")

		return result_view

	@staticmethod
	def isResultView(view):
		return view.settings().get("review_myself_view", False) == True

class ReviewMyselfShowResultCommand(sublime_plugin.TextCommand):
	def run(self, edit, **args):
		paths_to_search = args.get("paths_to_search", [])
		results = args.get("results", [])
		results = sorted(results, key=lambda result: (result['priority'])) # sort by priority
		#TODO: implement todo group by "From" #p2
		processed_file_count = args.get("processed_file_count", 0)
		processed_time = args.get("processed_time", 0)

		result_view = ResultView.get()
		result_view.erase(edit, sublime.Region(0, result_view.size()))

		result_view.settings().set("paths_to_search", paths_to_search)

		search_session_info = ""
		search_session_info += "{0:12} [".format("# From:")
		for index, path_to_search in enumerate(paths_to_search, 1):
			search_session_info += "{0}".format(Util.getBasenameFromPath(path_to_search))
			if index != len(paths_to_search):
				search_session_info += ", "
		search_session_info += "]\n"
		search_session_info += "{0:12} {1}\n".format("# No.Files:", processed_file_count)
		search_session_info += "{0:12} {1}s\n".format("# Time:", processed_time)
		search_session_info += "\n\n"

		result_view.insert(edit, result_view.size(), search_session_info)

		settings = Settings(self.view, "ReviewMyself")

		#TODO: remove linenum from result view by default #p1
		todo_result_pattern = ""
		todo_result_pattern += u"{index:<5}"
		todo_result_pattern += u"{filepath}"
		show_linenum = settings.get("show_linenum", False)
		if show_linenum:
			todo_result_pattern += u":{linenum:<5}"
		todo_result_pattern += u" => "
		todo_result_pattern += u"{priority}"
		todo_result_pattern += u"{todo}"
		
		result_regions = []

		for index, result in enumerate(results, 1):
			minimized_filepath = result["filepath"]
			for path_to_search in paths_to_search:
				if minimized_filepath.startswith(path_to_search):
					minimized_filepath = minimized_filepath.replace(path_to_search, Util.getBasenameFromPath(path_to_search))

			formatted_result = todo_result_pattern.format(
				index = "{0}.".format(index),
				filepath = minimized_filepath,
				linenum = result['linenum'],
				priority = "p{0}.".format(result["priority"]) if result["priority"] != 9999 else "", #TODO: unhardcode max priority #p3
				todo = result["todo"])

			result_region_start = result_view.size()
			result_view.insert(edit, result_region_start, formatted_result)
			result_region_stop = result_view.size()
			result_view.insert(edit, result_view.size(), u'\n')

			result_regions.append(sublime.Region(result_region_start, result_region_stop))

		result_view.add_regions('result_regions', result_regions, '')

		region_to_result_dict = dict(('{0},{1}'.format(region.a, region.b), result) for region, result in zip(result_regions, results))
		result_view.settings().set('region_to_result_dict', region_to_result_dict)
		
		result_view.settings().set("selected_index", -1)
		result_view.run_command("review_myself_navigate_result", {"direction": "down"})

		#TODO: sync usage text with user key map settings #p3
		usage_text = ""
		usage_text += "\n\n"
		usage_text += "# Usage:\n"
		usage_text += "#\t {0:20} = next todo\n".format("s")
		usage_text += "#\t {0:20} = previous todo\n".format("w")
		usage_text += "#\t {0:20} = refresh result\n".format("r")
		usage_text += "#\t {0:20} = start edit in context panel\n".format("e")
		usage_text += "#\t {0:20} = finish edit in context panel\n".format("escape")
		usage_text += "#\t {0:20} = goto todo location\n".format("f or enter")
		usage_text += "#\t {0:20} = open context panel\n".format("d")
		usage_text += "#\t {0:20} = close context panel\n".format("a")
		usage_text += "#\t {0:20} = select todo\n".format("move caret, then tab")
		result_view.insert(edit, result_view.size(), usage_text)

		#TODO: implement on the fly settings #p2
		

		sublime.active_window().focus_view(result_view)

class SearchThread(threading.Thread):
	def __init__(self, search_engine, onSearchingDone):
		self.search_engine = search_engine
		self.onSearchingDone = onSearchingDone
		threading.Thread.__init__(self)

	def run(self):
		self.search_engine.counter.startTimer()
		results = list(self.search_engine.search())
		self.search_engine.counter.stopTimer()
		self.onSearchingDone(results, self.search_engine.counter)
					
class Counter():
	def __init__(self):
		self.current = 0
		self.start_time = 0
		self.stop_time = 0
		self.lock = threading.RLock()

	def __str__(self):
		return "{0}".format(self.current)

	def startTimer(self):
		self.start_time = timeit.default_timer()

	def stopTimer(self):
		self.stop_time = timeit.default_timer()

	def getDeltaTime(self):
		return round(self.stop_time - self.start_time, 2)

	def increment(self):
		with self.lock:
			self.current += 1
		sublime.status_message("ReviewMyself: {0} files processed".format(self.current))

class ReviewMyselfImpl(sublime_plugin.TextCommand):
	def run(self, edit, paths):
		settings = Settings(self.view, "ReviewMyself")

		self.paths_to_search = paths
		self.is_ignore_case = settings.get("is_ignore_case", True)
		self.todo_patterns = settings.get("todo_patterns", [])
		self.priority_patterns = settings.get("priority_patterns", [])
		self.ignored_dir_patterns = settings.get("ignored_dir_patterns", [])
		self.only_care_file_patterns = settings.get("only_care_file_patterns", [])

		self.search_engine = TodoSearchEngine()
		self.search_engine.paths_to_search = self.paths_to_search
		self.search_engine.todo_filter = re.compile("|".join(self.todo_patterns), re.IGNORECASE if self.is_ignore_case else 0)
		self.search_engine.priority_filter = re.compile("|".join(self.priority_patterns), re.IGNORECASE if self.is_ignore_case else 0)
		self.search_engine.ignored_dir_patterns = self.ignored_dir_patterns
		self.search_engine.only_care_file_patterns = self.only_care_file_patterns

		self.search_thread = SearchThread(self.search_engine, self.onSearchingDone)
		self.search_thread.start()

	def onSearchingDone(self, results, counter):
		self.view.run_command("review_myself_show_result", {
			"paths_to_search": self.paths_to_search,
			"results": results,
			"processed_file_count": counter.current,
			"processed_time": counter.getDeltaTime()
			})

class ReviewMyselfAutoModeCommand(sublime_plugin.TextCommand):
	def run(self, edit):
		self.view.run_command("review_myself_impl", {
			"paths": self.view.window().folders()
			})

class ReviewMyselfCommand(sublime_plugin.TextCommand):
	TAG = "ReviewMyself.ReviewMyselfCommand"

	def run(self, edit, mode):
		if mode == "auto":
			self.view.run_command("review_myself_auto_mode")
		elif mode == "manual":
			#TODO: implement manual mode #p3
			Util.status("ReviewMyself: Manual mode is under construction!")
		else:
			Util.status("ReviewMyself: '{0}' mode is not supported yet! What matter with your settings ?".format(mode))

class ReviewMyselfNavigateResultCommand(sublime_plugin.TextCommand):
	TAG = "ReviewMyself.ReviewMyselfNavigateResultCommand"

	def run(self, edit, direction):
		view_settings = self.view.settings()
		result_regions = self.view.get_regions("result_regions")
		result_region_cout = len(result_regions)

		if result_region_cout <= 0:
			return

		selected_index = int(view_settings.get("selected_index", -1))
		
		if direction == "up":
			selected_index -= 1
		elif direction == "down":
			selected_index += 1
		else:
			Util.status("ReviewMyself: Incorrect navigation direction. Check settings!")
			return

		if selected_index < 0:
			selected_index = result_region_cout - 1
		elif selected_index > result_region_cout - 1:
			selected_index = 0
		
		view_settings.set('selected_index', selected_index)
		
		selected_region = result_regions[selected_index]
		self.view.add_regions('selected_region', [selected_region], "selected", "", sublime.DRAW_SOLID_UNDERLINE|sublime.DRAW_NO_FILL)
		self.view.show(selected_region)

		settings = Settings(self.view, "ReviewMyself")
		if view_settings.get("auto_show_context", settings.get("auto_show_context", True)):
			self.view.run_command("review_myself_goto", {"preview": True})

class ReviewMyselfGotoCommand(sublime_plugin.TextCommand):
	TAG = "ReviewMyself.ReviewMyselfGotoCommand"

	def run(self, edit, preview = False, focus_on = False):
		view_settings = self.view.settings()
		result_regions = self.view.get_regions("result_regions")
		result_region_cout = len(result_regions)

		if result_region_cout <= 0:
			return

		selected_index = int(view_settings.get("selected_index", -1))
		if selected_index < 0 or selected_index > result_region_cout - 1:
			Util.status("ReviewMyself: Select a todo first!")
			return;

		selected_region = result_regions[selected_index]
		region_to_result_dict = self.view.settings().get('region_to_result_dict')

		result = region_to_result_dict.get('{0},{1}'.format(selected_region.a, selected_region.b)) # use dict.get() instead dict[] to avoid KeyError exception
		if result is not None:
			if preview:
				active_window = self.view.window()
				opened_file_view = active_window.find_open_file(result["filepath"])
				if opened_file_view is not None:
					opened_file_view.close()

				if active_window.num_groups() != 2:
					active_window.run_command("set_layout", {
						"cols": [0.0, 1.0],
						"rows": [0.0, 0.5, 1.0],
						"cells": [[0, 0, 1, 1], [0, 1, 1, 2]]
						})

				active_window.focus_group(1)

				new_view = active_window.open_file("{filepath}:{linenum}".format(filepath = result['filepath'], linenum = result['linenum']), sublime.ENCODED_POSITION|sublime.TRANSIENT)
				new_view.settings().set("review_myself_context_view", True)

				if focus_on == False:
					active_window.focus_group(0)
					active_window.focus_view(self.view)

			else:
				new_view = self.view.window().open_file("{filepath}:{linenum}".format(filepath = result['filepath'], linenum = result['linenum']), sublime.ENCODED_POSITION)

class ReviewMyselfRefreshResultCommand(sublime_plugin.TextCommand):
	TAG = "ReviewMyself.ReviewMyselfRefreshResultCommand"

	def run(self, edit):
		view_settings = self.view.settings()
		paths_to_search = view_settings.get("paths_to_search", [])

		self.view.run_command("review_myself_impl", {"paths": paths_to_search})

class ReviewMyselfReviewCurrentFileCommand(sublime_plugin.TextCommand):
	TAG = "ReviewMyself.ReviewMyselfReviewCurrentFileCommand"

	def run(self, edit):
		active_window = sublime.active_window()
		active_view = active_window.active_view()

		if active_view:
			file_name = active_view.file_name()
			if file_name:
				self.view.run_command("review_myself_impl", {"paths": [file_name]})

class ReviewMyselfSelectResultCommand(sublime_plugin.TextCommand):
	TAG = "ReviewMyself.ReviewMyselfSelectResultCommand"

	def run(self, edit):
		view_settings = self.view.settings()
		result_regions = self.view.get_regions("result_regions")
		result_region_cout = len(result_regions)

		if result_region_cout <= 0:
			return

		if self.view.sel():
			selected_region = self.view.line(self.view.sel()[0].end())
			if selected_region in result_regions:
				selected_index = result_regions.index(selected_region)
				view_settings.set('selected_index', selected_index)
		
				self.view.add_regions('selected_region', [selected_region], "selected", "", sublime.DRAW_SOLID_UNDERLINE|sublime.DRAW_NO_FILL)
				self.view.show(selected_region)

				settings = Settings(self.view, "ReviewMyself")
				if view_settings.get("auto_show_context", settings.get("auto_show_context", True)):
					self.view.run_command("review_myself_goto", {"preview": True})

class ReviewMyselfSetAutoShowContext(sublime_plugin.TextCommand):
	TAG = "ReviewMyself.ReviewMyselfToggleAutoShowContext"

	def run(self, edit, enable):
		view_settings = self.view.settings()
		view_settings.set("auto_show_context", enable)

		if enable:
			self.view.run_command("review_myself_goto", { "preview": True })			
		else:
			self.view.run_command("review_myself_close_context_panel")

class ReviewMyselfCloseContextPanel(sublime_plugin.TextCommand):
	TAG = "ReviewMyself.ReviewMyselfCloseContextView"

	def run(self, edit):
		self.view.window().run_command("set_layout", {
				"cols": [0.0, 1.0],
				"rows": [0.0, 1.0],
				"cells": [[0, 0, 1, 1]]
			})

class ReviewMyselfStartEditInContextPanel(sublime_plugin.TextCommand):
	TAG = "ReviewMyself.ReviewMyselfStartEditInContextPanel"

	def run(self, edit):
		self.view.run_command("review_myself_goto", { "preview": True, "focus_on": True })

class ReviewMyselfFinishEditInContextPanel(sublime_plugin.TextCommand):
	TAG = "ReviewMyself.ReviewMyselfFinishEditInContextPanel"

	def run(self, edit):
		active_window = self.view.window()
		settings = Settings(self.view, "ReviewMyself")
		result_view = ResultView.get()
		result_view_settings = result_view.settings()
		auto_show_context = result_view_settings.get("auto_show_context", settings.get("auto_show_context", True))
		if auto_show_context == False:
			self.view.run_command("review_myself_close_context_panel")
			for view in active_window.views():
				if view.settings().get("review_myself_context_view", False):
					view.close()
					break

		active_window.focus_group(0)