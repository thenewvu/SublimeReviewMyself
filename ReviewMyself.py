import sublime_plugin
import sublime
import os
import threading
import functools
import fnmatch
import re
import sys
import timeit
import ntpath

class Util():
	@staticmethod
	def log(tag, message):
		print("{tag}: {message}".format(tag = tag, message = message))

	@staticmethod
	def status(message):
		sublime.status_message("{message}".format(message = message))

class Settings():
	def __init__(self, view, setting_name):
		self.default = sublime.load_settings("{setting_name}.sublime-settings".format(setting_name = setting_name))
		self.user = view.settings().get("{setting_name}".format(setting_name = setting_name), {})
		print(self.default)
		print(self.user)

	def get(self, fieldName, defaultValue):
		return self.user.get(fieldName, self.default.get(fieldName, defaultValue))

class TodoSearchEngine():
	TAG = "ReviewMyself.TodoSearchEngine"

	def __init__(self):
		self.paths_to_search = []
		self.todo_filter = None
		self.priority_filter = None
		self.exclude_patterns = ["*.jpg", "*.jpeg", "*.png", "*.gif", "*.ttf", "*.tga", "*.dds", "*.ico",
								"*.eot", "*.pdf", "*.swf", "*.jar", "*.zip", "*.pyc", "*.pyo", "*.exe",
								"*.dll", "*.obj","*.o", "*.a", "*.lib", "*.so", "*.dylib", "*.ncb",
								"*.sdf", "*.suo", "*.pdb", "*.idb", ".DS_Store", "*.class", "*.psd",
								"*.db", "*.sublime-workspace",
								".svn", ".git", ".hg", "CVS"]
		self.counter = Counter()

	def basename(self, path):
		head, tail = ntpath.split(path)
		return tail or ntpath.basename(head)

	def isIgnoredName(self, name):
		for pattern in self.exclude_patterns:
			if fnmatch.fnmatch(name, pattern):
				return True
		return False

	def filterNames(self, names):
		filtered_names = []
		for name in names:
			if not self.isIgnoredName(name):
				filtered_names.append(name)
		return filtered_names

	def walk(self):
		for path_to_search in self.paths_to_search:
			path_to_search = os.path.realpath(os.path.expanduser(os.path.abspath(path_to_search)))
			if os.path.exists(path_to_search):
				if os.path.isfile(path_to_search):
					filename = self.basename(path_to_search)
					if not self.isIgnoredName(filename):
						yield path_to_search
				for dirpath, dirnames, filenames in os.walk(path_to_search, topdown = True):
					dirnames[:] = self.filterNames(dirnames)
					filenames[:] = self.filterNames(filenames)
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
						if "todo" not in match_groups:
							Util.status("Wrong todo pattern! What matter with your settings ?")
							return

						todo = match_groups["todo"]

						#TODO: process priority
						# priority = self.priority_filter.search(todo)
						priority = 100

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
		existed_result_view = [view for view in active_window.views() if view.name() == 'ReviewMyself' and view.is_scratch()]
		if existed_result_view:
			result_view = existed_result_view[0]
		else:
			result_view = active_window.new_file()
			result_view.set_name('ReviewMyself')
			result_view.set_scratch(True)
			result_view.settings().set('review_myself_view', True)
			result_view.settings().set('command_mode', True)
			result_view.settings().set('word_wrap', False)
			result_view.settings().set("line_numbers", False)
			result_view.assign_syntax('Packages/ReviewMyself/ReviewMyself.hidden-tmLanguage')

		return result_view

class ReviewMyselfShowResultCommand(sublime_plugin.TextCommand):
	def run(self, edit, **args):
		paths_to_search = args.get("paths_to_search", [])
		results = args.get("results", [])
		results = sorted(results, key=lambda result: (result['priority'])) # sort by proority
		processed_file_count = args.get("processed_file_count", 0)
		processed_time = args.get("processed_time", 0)

		result_view = ResultView.get()
		result_view.erase(edit, sublime.Region(0, result_view.size()))

		hr = "-" * 50 + "\n"
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
		return self.stop_time - self.start_time

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
		Util.log("vu.lethanh", self.todo_patterns)
		self.priority_patterns = settings.get("priority_patterns", [])

		self.search_engine = TodoSearchEngine()
		self.search_engine.paths_to_search = self.paths_to_search
		self.search_engine.todo_filter = re.compile("|".join(self.todo_patterns), re.IGNORECASE if self.is_ignore_case else 0)
		self.search_engine.priority_filter = re.compile("|".join(self.priority_patterns), re.IGNORECASE if self.is_ignore_case else 0)

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
			#TODO: implement manual mode
			Util.status("manual mode is under construction!")
		else:
			Util.status("'{0}' mode is not supported yet! What matter with your settings ?".format(mode))

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

class ReviewMyselfGotoCommand(sublime_plugin.TextCommand):
	TAG = "ReviewMyself.ReviewMyselfGotoCommand"

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
		new_view = self.view.window().open_file("{filepath}:{linenum}".format(filepath = result['filepath'], linenum = result['linenum']), sublime.ENCODED_POSITION)