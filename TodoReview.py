'''
SublimeTodoReview
A SublimeText 3 plugin for reviewing todo (any other) comments within your code.

@author Jonathan Delgado (Initial Repo by @robcowie and ST3 update by @dnatag)
'''

from collections import namedtuple
from datetime import datetime
from itertools import groupby
from os import path, walk
import sublime_plugin
import threading
import sublime
import functools
import fnmatch
import re
import sys
import timeit

Result = namedtuple('Result', 'match_name, match_text')


def do_when(conditional, callback, *args, **kwargs):
	if conditional():
		return callback(*args, **kwargs)
	sublime.set_timeout(functools.partial(do_when, conditional, callback, *args, **kwargs), 50)

class Util():
	@staticmethod
	def log(message):
		print("ReviewMyself: {0}".format(message))

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
				for linenum, line in enumerate(file_stream):
					for mo in self.todo_filter.finditer(line):
						matches = [Result(match_name, match_text) for match_name, match_text in mo.groupdict().items() if match_text]
						for match in matches:
							priority = self.priority_filter.search(match.match_text)

							if priority:
								priority = int(priority.group(0).replace('(', '').replace(')', ''))
							else:
								priority = 100

							yield {
								'filepath': filepath,
								'linenum': linenum + 1,
								'match': match,
								'priority': priority
							}
			except:
				Util.log("Read error, file: {0}, reason: {1}".format(filepath, sys.exc_info()))
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

		regions_data = [x[:] for x in [[]] * 2]

		results = sorted(results, key=lambda result: (result['priority']))
		for index, result in enumerate(results, 1):
			insert_point = result_view.size()

			formatted_result = u'{index}. {filepath}:{linenum} => {todo}'.format(
				index = index,
				filepath = result["filepath"],
				linenum = result['linenum'],
				todo = result["match"][1])

			result_view.insert(edit, insert_point, formatted_result)

			region = sublime.Region(insert_point, result_view.size())
			regions_data[0].append(region)
			regions_data[1].append(result)
			result_view.insert(edit, result_view.size(), u'\n')

		result_view.add_regions('results', regions_data[0], '')

		d_ = dict(('{0},{1}'.format(k.a, k.b), v) for k, v in zip(regions_data[0], regions_data[1]))
		result_view.settings().set('result_regions', d_)

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

class NavigateResults(sublime_plugin.TextCommand):
	def __init__(self, view):
		super(NavigateResults, self).__init__(view)

	def run(self, edit, direction):
		view_settings = self.view.settings()
		results = self.view.get_regions('results')

		start_arr = {
			'forward': -1,
			'backward': 0,
			'forward_skip': -1,
			'backward_skip': 0
		}

		dir_arr = {
			'forward': 1,
			'backward': -1,
			'forward_skip': settings.get('navigation_forward_skip', 10),
			'backward_skip': settings.get('navigation_backward_skip', 10) * -1
		}

		if not results:
			sublime.status_message('No results to navigate')
			return

		selection = int(view_settings.get('selected_result', start_arr[direction]))
		selection = selection + dir_arr[direction]

		try:
			target = results[selection]
		except IndexError:
			if selection < 0:
				target = results[0]
				selection = 0
			else:
				target = results[len(results) - 1]
				selection = len(results) - 1

		view_settings.set('selected_result', selection)
		target = target.cover(target)
		self.view.add_regions('selection', [target], 'selected', 'dot')
		target.b = target.a + 5
		self.view.show(target)

class ClearSelection(sublime_plugin.TextCommand):
	def run(self, edit):
		self.view.erase_regions('selection')
		self.view.settings().erase('selected_result')

class GotoComment(sublime_plugin.TextCommand):
	def __init__(self, *args):
		super(GotoComment, self).__init__(*args)

	def run(self, edit):
		selection = int(self.view.settings().get('selected_result', -1))
		selected_region = self.view.get_regions('results')[selection]

		data = self.view.settings().get('result_regions')['{0},{1}'.format(selected_region.a, selected_region.b)]
		new_view = self.view.window().open_file(data['filepath'])
		do_when(lambda: not new_view.is_loading(), lambda:new_view.run_command('goto_line', {'line': data['linenum']}))

class MouseGotoComment(sublime_plugin.TextCommand):
    def __init__(self, *args):
        super(MouseGotoComment, self).__init__(*args)

    def run(self, edit):
        if not self.view.settings().get('result_regions'):
            return

        result = self.view.line(self.view.sel()[0].end())

        target = result.cover(result)
        self.view.add_regions('selection', [target], 'selected', 'dot')
        self.view.show(target)

        data = self.view.settings().get('result_regions')['{0},{1}'.format(result.a, result.b)]
        new_view = self.view.window().open_file(data['filepath'])
        do_when(lambda: not new_view.is_loading(), lambda: new_view.run_command("goto_line", {"line": data['linenum']}))