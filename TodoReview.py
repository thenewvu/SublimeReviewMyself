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

Result = namedtuple('Result', 'match_name, match_text')


def do_when(conditional, callback, *args, **kwargs):
	if conditional():
		return callback(*args, **kwargs)
	sublime.set_timeout(functools.partial(do_when, conditional, callback, *args, **kwargs), 50)

class Settings():
	def __init__(self, view):
		self.user = sublime.load_settings('TodoReview.sublime-settings')
		self.view = view.settings().get('todoreview', {})

	def get(self, item, default):
		return self.view.get(item, self.user.get(item, default))

class TodoSearchEngine(object):
	def __init__(self, paths_to_search, counter):
		self.paths_to_search = paths_to_search
		self.patterns = settings.get('patterns', {})
		self.counter = counter

	def walk(self):
		for path_to_search in self.paths_to_search:
			path_to_search = path.abspath(path_to_search)
			for dirpath, dirnames, filenames in walk(path_to_search):
				for filename in filenames:
					filepath = path.join(dirpath, filename)
					filepath = path.realpath(path.expanduser(path.abspath(filepath)))
					yield filepath

	def search(self):
		todo_pattern = '|'.join(self.patterns.values())
		case_sensitivity = 0 if settings.get('case_sensitive', False) else re.IGNORECASE
		todo_filter = re.compile(todo_pattern, case_sensitivity)
		priority_filter = re.compile(r'\(([0-9]{1,2})\)')

		for filepath in self.walk():
			try:
				file_stream = open(filepath, 'r', encoding='utf-8')
				for linenum, line in enumerate(file_stream):
					for mo in todo_filter.finditer(line):
						matches = [Result(match_name, match_text) for match_name, match_text in mo.groupdict().items() if match_text]
						for match in matches:
							priority = priority_filter.search(match.match_text)

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
				print("Can not read {0}, because: {1}".format(filepath, sys.exc_info()))
				file_stream = None
			finally:
				self.counter.increment()
				if file_stream is not None:
					file_stream.close()

class RenderResultRunCommand(sublime_plugin.TextCommand):
	def run(self, edit, formatted_results, file_counter):
		active_window = sublime.active_window()
		existing_results = [v for v in active_window.views() if v.name() == 'TodoReview' and v.is_scratch()]
		if existing_results:
			result_view = existing_results[0]
		else:
			result_view = active_window.new_file()
			result_view.set_name('TodoReview')
			result_view.set_scratch(True)
			result_view.settings().set('todo_results', True)

		hr = u'+ {0} +'.format('-' * 56)
		header = u'{hr}\n| TodoReview @ {0:<43} |\n| {1:<56} |\n{hr}\n'.format(datetime.now().strftime('%A %m/%d/%y at %I:%M%p'), u'{0} files scanned'.format(file_counter), hr=hr)

		result_view.erase(edit, sublime.Region(0, result_view.size()))
		result_view.insert(edit, result_view.size(), header)

		regions_data = [x[:] for x in [[]] * 2]


		for linetype, line, data in formatted_results:
			insert_point = result_view.size()
			result_view.insert(edit, insert_point, line)
			if linetype == 'result':
				rgn = sublime.Region(insert_point, result_view.size())
				regions_data[0].append(rgn)
				regions_data[1].append(data)
			result_view.insert(edit, result_view.size(), u'\n')

		result_view.add_regions('results', regions_data[0], '')

		d_ = dict(('{0},{1}'.format(k.a, k.b), v) for k, v in zip(regions_data[0], regions_data[1]))
		result_view.settings().set('result_regions', d_)

		result_view.assign_syntax('Packages/TodoReview/TodoReview.hidden-tmLanguage')
		result_view.settings().set('line_padding_bottom', 2)
		result_view.settings().set('line_padding_top', 2)
		result_view.settings().set('word_wrap', False)
		result_view.settings().set('command_mode', True)
		active_window.focus_view(result_view)

class SearchThread(threading.Thread):
	def __init__(self, search_engine, callback, counter):
		self.search_engine = search_engine
		self.callback = callback
		self.counter = counter
		threading.Thread.__init__(self)

	def run(self):
		result = self.search_engine.search()
		formatted_result = list(self.format(result))
		self.callback(formatted_result, self.counter)

	def format(self, result):
		result = sorted(result, key=lambda m: (m['priority'], m['match'].match_name))

		for match_name, matches in groupby(result, key=lambda m: m['match'].match_name):
			matches = list(matches)
			if matches:
				yield ('header', u'\n## {0} ({1})'.format(match_name.upper(), len(matches)), {})
				for idx, m in enumerate(matches, 1):
					match_text = m['match'].match_text

					filepath = path.dirname(m['filepath']).replace('\\', '/').split('/')
					filepath = filepath[len(filepath) - 1]  + '/' + path.basename(m['filepath'])

					spaces = ' '*(settings.get('render_spaces', 1) - len(str(idx) + filepath + ':' + str(m['linenum'])))
					line = u'{idx}. {filepath}:{linenum}{spaces}{match_text}'.format(idx=idx, filepath=filepath, linenum=m['linenum'], spaces=spaces, match_text=match_text)
					yield ('result', line, m)

class Counter(object):
	def __init__(self):
		self.current = 0
		self.lock = threading.RLock()

	def __str__(self):
		return "{0}".format(self.current)

	def increment(self):
		with self.lock:
			self.current += 1
		sublime.status_message("TodoReview: {0} files processed".format(self.current))

class TodoReviewImpl(sublime_plugin.TextCommand):
	def run(self, edit, **args):
		self.paths_to_search = args["paths_to_search"]
		print("\n".join(self.paths_to_search))

		self.counter = Counter()
		search_engine = TodoSearchEngine(self.paths_to_search, self.counter)

		worker_thread = SearchThread(search_engine, self.onSearchingDone, self.counter)
		worker_thread.start()

	def onSearchingDone(self, rendered, counter):
		self.view.run_command('render_result_run', {'formatted_results': rendered, 'file_counter': str(self.counter)})

class TodoReviewAutoModeCommand(sublime_plugin.TextCommand):
	def run(self, edit, **args):
		self.view.run_command("todo_review_impl", {
			"paths_to_search": self.view.window().folders()
			})

class TodoReviewCommand(sublime_plugin.TextCommand):
	def run(self, edit, **args):
		if args["mode"] == "auto":
			self.view.run_command("todo_review_auto_mode")
		elif args["mode"] == "manual":
			#TODO: implement manual mode
			print("implement manual mode")
		else:
			print("\"{0}\" mode is not supported yet!".format(str(args["mode"])))

		global settings

		filepaths = []
		settings = Settings(self.view)
		self.window = self.view.window()

		# if not paths:
		# 	if settings.get('include_paths', False):
		# 		paths = settings.get('include_paths', False)

		# if open_files:
		# 	filepaths = [view.file_name() for view in self.window.views() if view.file_name()]

		# if not open_files_only:
		# 	if not paths:
		# 		paths = self.window.folders()
		# 	else:
		# 		for p in paths:
		# 			if path.isfile(p):
		# 				filepaths.append(p)
		# else:
		# 	paths = []

		# file_counter = Counter()
		# search_engine = TodoSearchEngine(paths, filepaths, file_counter)

		# worker_thread = SearchThread(search_engine, self.render_formatted, file_counter)
		# worker_thread.start()
		# ThreadProgress(worker_thread, 'Finding TODOs', '', file_counter)

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