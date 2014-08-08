'''
SublimeTodoReview
A SublimeText 3 plugin for reviewing todo (any other) comments within your code.

@author Jonathan Delgado (Initial Repo by @robcowie and ST3 update by @dnatag)
'''

from os import path, walk
import sublime_plugin
import sublime
import threading
import functools
import fnmatch
import re
import sys
import timeit

class Util():
	@staticmethod
	def log(message):
		print("ReviewMyself: {0}".format(message))

	@staticmethod
	def status(message):
		sublime.status_message("ReviewMyself: {0}".format(message))

	@staticmethod
	def doWhenSomethingDone(condition, callback, *args, **kwargs):
		if condition():
			return callback(*args, **kwargs)
		sublime.set_timeout(functools.partial(Util.doWhenSomethingDone, condition, callback, *args, **kwargs), 50)

class Settings():
	def __init__(self, view):
		self.user = sublime.load_settings('TodoReview.sublime-settings') #TODO: change file name
		self.default = view.settings().get('todoreview', {}) #TODO: change setting name

	def get(self, field, defaultValue):
		return self.default.get(field, self.user.get(field, defaultValue))

class TodoSearchEngine(object):
	def __init__(self):
		self.paths_to_search = []
		self.todo_filter = None
		self.priority_filter = None
		self.counter = Counter()

	def walk(self):
		for path_to_search in self.paths_to_search:
			path_to_search = path.abspath(path_to_search)
			for dirpath, dirnames, filenames in walk(path_to_search):
				for filename in filenames:
					filepath = path.join(dirpath, filename)
					filepath = path.realpath(path.expanduser(path.abspath(filepath)))
					yield filepath

	def search(self):
		for filepath in self.walk():
			try:
				file_stream = open(filepath, 'r', encoding='utf-8')
				for linenum, line in enumerate(file_stream, 1):
					for matches in self.todo_filter.finditer(line):
						for match_name, match_text in matches.groupdict().items():
							priority = self.priority_filter.search(match_text)

							if priority:
								priority = int(priority.group(0).replace('(', '').replace(')', ''))
							else:
								priority = 100

							yield {
								'filepath': filepath,
								'linenum': linenum,
								'todo': match_text,
								'priority': priority
							}
			except:
				# Util.log("Read error, file: {0}, reason: {1}".format(filepath, sys.exc_info()))
				Util.log("Can not read {0}".format(filepath))
				file_stream = None
			finally:
				self.counter.increment()
				if file_stream is not None:
					file_stream.close()

class ResultView():
	@staticmethod
	def get():
		active_window = sublime.active_window()
		#TODO: change result view attributes
		existed_result_view = [view for view in active_window.views() if view.name() == 'TodoReview' and view.is_scratch()]
		if existed_result_view:
			result_view = existed_result_view[0]
		else:
			result_view = active_window.new_file()
			result_view.set_name('TodoReview')
			result_view.set_scratch(True)
			result_view.settings().set('line_padding_bottom', 2)
			result_view.settings().set('line_padding_top', 2)
			result_view.settings().set('word_wrap', False)
			result_view.settings().set('command_mode', True)
			result_view.settings().set('todo_results', True)
			result_view.assign_syntax('Packages/TodoReview/TodoReview.hidden-tmLanguage')

		return result_view

class TodoReviewShowResultCommand(sublime_plugin.TextCommand):
	def run(self, edit, **args):
		paths_to_search = args.get("paths_to_search", [])
		results = args.get("results", [])
		results = sorted(results, key=lambda result: (result['priority'])) # sort by proority
		processed_file_count = args.get("processed_file_count", 0)
		processed_time = args.get("processed_time", 0)

		result_view = ResultView.get()
		result_view.erase(edit, sublime.Region(0, result_view.size()))

		hr = "-" * 100 + "\n"
		search_session_info = ""

		search_session_info += hr
		search_session_info += "Searched in:\n"
		for path_to_search in paths_to_search:
			search_session_info += "\t{0}\n".format(path_to_search)
		search_session_info += "Processed file count: {0}\n".format(processed_file_count)
		search_session_info += "Processed time: {0}s\n".format(processed_time)
		search_session_info += hr

		result_view.insert(edit, result_view.size(), search_session_info)
		
		result_regions = []

		for index, result in enumerate(results, 1):
			formatted_result = u'{index}. {filepath}:{linenum} => {todo}'.format(
				index = index,
				filepath = result["filepath"],
				linenum = result['linenum'],
				todo = result["todo"])

			result_region_start = result_view.size()
			result_view.insert(edit, result_region_start, formatted_result)
			result_region_stop = result_view.size()
			result_view.insert(edit, result_view.size(), u'\n')

			result_regions.append(sublime.Region(result_region_start, result_region_stop))

		result_view.add_regions('result_regions', result_regions, '')

		region_to_result_dict = dict(('{0},{1}'.format(region.a, region.b), result) for region, result in zip(result_regions, results));
		result_view.settings().set('region_to_result_dict', region_to_result_dict)
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
					
class Counter(object):
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
		return self.stop_time - self.start_time

	def increment(self):
		with self.lock:
			self.current += 1
		sublime.status_message("TodoReview: {0} files processed".format(self.current))

class TodoReviewImpl(sublime_plugin.TextCommand):
	def run(self, edit, **args):
		global settings
		settings = Settings(self.view)

		self.paths_to_search = args.get("paths_to_search", [])
		self.is_ignore_case = settings.get("is_ignore_case", True)
		self.todo_patterns = settings.get("todo_patterns", [])
		self.priority_patterns = settings.get("priority_patterns", [])

		Util.log("paths_to_search = {0}".format(self.paths_to_search))

		self.search_engine = TodoSearchEngine()
		self.search_engine.paths_to_search = self.paths_to_search
		self.search_engine.todo_filter = re.compile("|".join(self.todo_patterns), re.IGNORECASE if self.is_ignore_case else 0)
		self.search_engine.priority_filter = re.compile("|".join(self.priority_patterns), re.IGNORECASE if self.is_ignore_case else 0)

		self.search_thread = SearchThread(self.search_engine, self.onSearchingDone)
		self.search_thread.start()

	def onSearchingDone(self, results, counter):
		self.view.run_command("todo_review_show_result", {
			"paths_to_search": self.paths_to_search,
			"results": results,
			"processed_file_count": counter.current,
			"processed_time": counter.getDeltaTime()
			})

class TodoReviewAutoModeCommand(sublime_plugin.TextCommand):
	def run(self, edit, **args):
		self.view.run_command("todo_review_impl", {
			"paths_to_search": self.view.window().folders()
			})

class TodoReviewCommand(sublime_plugin.TextCommand):
	def run(self, edit, **args):		
		if "mode" in args:
			self.mode = args["mode"]
		else:
			self.mode = "auto"

		if self.mode == "auto":
			self.view.run_command("todo_review_auto_mode")
		elif self.mode == "manual":
			#TODO: implement manual mode
			Util.log("manual mode is under construction!")
		else:
			Util.log("\"{0}\" mode is not supported yet!".format(self.mode))

	def render_formatted(self, rendered, counter):
		self.window.run_command('render_result_run', {'formatted_results': rendered, 'file_counter': str(counter)})

class TodoReviewNavigateResultCommand(sublime_plugin.TextCommand):
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
			Util.status("Incorrect navigation direction. Check settings!")
			return

		if selected_index < 0:
			selected_index = result_region_cout - 1
		elif selected_index > result_region_cout - 1:
			selected_index = 0
		
		view_settings.set('selected_index', selected_index)
		
		selected_region = result_regions[selected_index]
		self.view.add_regions('selected_region', [selected_region], 'selected', 'dot')
		self.view.show(selected_region)

class TodoReviewGotoCommand(sublime_plugin.TextCommand):
	def run(self, edit):
		view_settings = self.view.settings()
		result_regions = self.view.get_regions("result_regions")
		result_region_cout = len(result_regions)

		if result_region_cout <= 0:
			return

		selected_index = int(view_settings.get("selected_index", -1))
		if selected_index < 0 or selected_index > result_region_cout - 1:
			Util.status("Select a todo first!")
			return;

		selected_region = result_regions[selected_index]
		region_to_result_dict = self.view.settings().get('region_to_result_dict')

		result = region_to_result_dict['{0},{1}'.format(selected_region.a, selected_region.b)]
		new_view = self.view.window().open_file(result['filepath'])
		Util.doWhenSomethingDone(lambda: not new_view.is_loading(), lambda:new_view.run_command('goto_line', {'line': result['linenum']}))

# Reference: https://github.com/bradrobertson/sublime-packages/blob/master/Default/goto_line.py
class GotoLineCommand(sublime_plugin.TextCommand):
	def run(self, edit, line):
		# Convert from 1 based to a 0 based line number
		line = int(line) - 1

		# Negative line numbers count from the end of the buffer
		if line < 0:
			lines, _ = self.view.rowcol(self.view.size())
			line = lines + line + 1

		pt = self.view.text_point(line, 0)

		self.view.sel().clear()
		self.view.sel().add(sublime.Region(pt))

		self.view.show_at_center(pt)