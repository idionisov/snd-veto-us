import os
import sys
from typing import List, Union, Optional, Set, Sequence, Dict, Any, Tuple
import ROOT


_LIBRARIES_LOADED = False


def load_analysis_libraries(repo_root: Optional[str] = None):
    global _LIBRARIES_LOADED
    if _LIBRARIES_LOADED:
        return
    _LIBRARIES_LOADED = True

    if repo_root is None:
        repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    build_lib = os.path.join(repo_root, "build", "lib")
    analysis_inc = os.path.join(repo_root, "analysis")

    ROOT.gInterpreter.AddIncludePath(analysis_inc)

    sndsw_root = os.environ.get("SNDSW_ROOT", "")
    if sndsw_root:
        ROOT.gInterpreter.AddIncludePath(os.path.join(sndsw_root, "include"))
        ROOT.gInterpreter.AddIncludePath(os.path.join(sndsw_root, "analysis/tools"))
        for h_tool in ["sndGeometryGetter.h", "sndTchainGetter.h", "sndConfiguration.h"]:
            for d in [os.path.join(sndsw_root, "include"), os.path.join(sndsw_root, "analysis/tools")]:
                ht_path = os.path.join(d, h_tool)
                if os.path.exists(ht_path):
                    ROOT.gInterpreter.ProcessLine(f'#include "{ht_path}"')
                    break

    for h_name in ["DataManager.h"]:
        header_file = os.path.join(analysis_inc, h_name)
        if os.path.exists(header_file):
            ROOT.gInterpreter.ProcessLine(f'#include "{header_file}"')

    ROOT.gSystem.AddDynamicPath(build_lib)

    for lib_name in ["libsnd_analysis.so", "libsnd_analysis_tools.so"]:
        lib_path = os.path.join(build_lib, lib_name)
        if os.path.exists(lib_path):
            ROOT.gSystem.Load(lib_path)


load_libraries = load_analysis_libraries


class DataManager:
    def __init__(
        self,
        source: Optional[Union[str, Sequence[str], int, ROOT.TChain]] = None,
        tree_name: Optional[str] = None,
        num_threads: Optional[int] = None,
        run: Optional[int] = None,
        n_files: int = -1,
        csv_data_path: Optional[str] = None,
        geo_path: Optional[str] = None,
        csv_geo_path: Optional[str] = None,
        init_geo: bool = False,
        load_libraries: bool = True,
    ):
        if load_libraries:
            load_analysis_libraries()

        tree_str = tree_name if tree_name is not None else ""
        threads_int = num_threads if (num_threads is not None and num_threads > 0) else 0

        # Determine run number if provided
        run_num: Optional[int] = None
        if run is not None:
            run_num = int(run)
        elif isinstance(source, int):
            run_num = int(source)

        if run_num is not None:
            if csv_data_path is None:
                repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                default_csv = os.path.join(repo_root, "config", "data_paths.csv")
                csv_str = default_csv if os.path.exists(default_csv) else ""
            else:
                csv_str = str(csv_data_path)
            self._cpp = ROOT.snd.DataManager(run_num, n_files, csv_str, tree_str, threads_int)
        elif isinstance(source, ROOT.TChain):
            self._cpp = ROOT.snd.DataManager(source, False, threads_int)
        elif isinstance(source, (list, tuple)):
            files = list(source)
            if n_files > 0:
                files = files[:n_files]
            vec = ROOT.std.vector('string')()
            for s in files:
                vec.push_back(str(s))
            self._cpp = ROOT.snd.DataManager(vec, tree_str, threads_int)
        elif source is not None:
            if n_files > 0:
                resolved = list(ROOT.snd.DataManager.ResolveFiles(str(source)))
                vec = ROOT.std.vector('string')()
                for s in resolved[:n_files]:
                    vec.push_back(str(s))
                self._cpp = ROOT.snd.DataManager(vec, tree_str, threads_int)
            else:
                self._cpp = ROOT.snd.DataManager(str(source), tree_str, threads_int)
        else:
            self._cpp = ROOT.snd.DataManager()

        if geo_path:
            self._cpp.SetGeoPath(str(geo_path))

        if init_geo:
            self.init_geometry(geo_path=geo_path, csv_file_path=csv_geo_path)

        self._branch_names: Optional[Set[str]] = None

    @property
    def tree_name(self) -> str:
        return str(self._cpp.GetTreeName())

    @property
    def files(self) -> List[str]:
        return [str(f) for f in self._cpp.GetFiles()]

    @property
    def num_files(self) -> int:
        return int(self._cpp.GetNumFiles())

    @property
    def branch_names(self) -> Set[str]:
        if self._branch_names is None:
            self._branch_names = set([str(b) for b in self._cpp.GetBranchNamesList()])
        return self._branch_names

    def has_branch(self, name: str) -> bool:
        return bool(self._cpp.HasBranch(name))

    def has_event_header(self) -> bool:
        return bool(self._cpp.HasEventHeader())

    @property
    def run_number(self) -> Optional[int]:
        rn = int(self._cpp.GetRunNumber())
        return rn if rn > 0 else None

    @property
    def fill_number(self) -> Optional[int]:
        fn = int(self._cpp.GetFillNumber())
        return fn if fn > 0 else None

    def get_fill_number(self) -> Optional[int]:
        return self.fill_number

    @property
    def lumi_path(self) -> Optional[str]:
        p = str(self._cpp.GetLumiPath())
        return p if p else None

    def get_lumi_path(self, lumi_dir: str = "/eos/experiment/sndlhc/atlas_lumi") -> Optional[str]:
        p = str(self._cpp.GetLumiPath(lumi_dir))
        return p if p else None

    @property
    def data_base_path(self) -> Optional[str]:
        dbp = str(self._cpp.GetDataBasePath())
        return dbp if dbp else None

    @property
    def geo_path(self) -> Optional[str]:
        gp = str(self._cpp.GetGeoPath())
        return gp if gp else None

    @geo_path.setter
    def geo_path(self, path: str) -> None:
        self._cpp.SetGeoPath(str(path))

    def get_geo_path(self, csv_file_path: Optional[str] = None) -> Optional[str]:
        gp = str(self._cpp.GetGeoPath(csv_file_path or ""))
        return gp if gp else None

    def init_geometry(self, geo_path: Optional[str] = None, csv_file_path: Optional[str] = None) -> Tuple[Any, Any]:
        repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        default_csv = os.path.join(repo_root, "config", "geo_paths.csv")
        csv_to_use = csv_file_path or (default_csv if os.path.exists(default_csv) else "")
        geom = self._cpp.InitGeometry(geo_path or "", csv_to_use)
        return (geom.first, geom.second)

    @property
    def has_geometry(self) -> bool:
        return bool(self._cpp.HasGeometry())

    @property
    def scifi(self) -> Any:
        return self._cpp.GetScifi()

    @property
    def mufilter(self) -> Any:
        return self._cpp.GetMuFilter()

    @property
    def geometry(self) -> Tuple[Any, Any]:
        g = self._cpp.GetGeometry()
        return (g.first, g.second)

    @property
    def configuration(self) -> Optional[Any]:
        cfg = self._cpp.GetConfiguration()
        return cfg if cfg else None

    def isMC(self) -> bool:
        return bool(self._cpp.IsMC())

    @property
    def is_mc(self) -> bool:
        return self.isMC()

    @property
    def entries(self) -> int:
        return int(self._cpp.GetEntries())

    def __len__(self) -> int:
        return self.entries

    def get_chain(self) -> ROOT.TChain:
        return self._cpp.GetChain()

    def rdf(
        self,
        range_limit: Optional[int] = None,
    ) -> ROOT.RDataFrame:
        dataframe = self._cpp.GetDataFrame()
        if range_limit is not None and range_limit > 0:
            dataframe = dataframe.Range(range_limit)
        return dataframe

    def get_rdataframe(self, range_limit: Optional[int] = None) -> ROOT.RDataFrame:
        return self.rdf(range_limit=range_limit)

    @property
    def rdataframe(self) -> ROOT.RDataFrame:
        return self.rdf()

    def get_time_range(self, cached: bool = True) -> Optional[Tuple[int, int]]:
        tr = self._cpp.GetTimeRange(cached)
        if tr.first > 0 and tr.second > 0:
            return (int(tr.first), int(tr.second))
        return None

    def get_duration(self, cached: bool = True) -> Optional[float]:
        dur = self._cpp.GetDuration(cached)
        return float(dur) if dur >= 0.0 else None

    @property
    def duration(self) -> Optional[float]:
        return self.get_duration()

    @property
    def time_range(self) -> Optional[Tuple[int, int]]:
        return self.get_time_range()

    def get_duration_str(self, cached: bool = True) -> Optional[str]:
        dur_str = str(self._cpp.GetDurationStr(cached))
        return dur_str if dur_str and dur_str != "N/A" else None

    def get_time_range_fast(self, cached: bool = True) -> Optional[Tuple[int, int]]:
        tr = self._cpp.GetTimeRangeFast(cached)
        if tr.first > 0 and tr.second > 0:
            return (int(tr.first), int(tr.second))
        return None

    def get_duration_fast(self, cached: bool = True) -> Optional[float]:
        dur = self._cpp.GetDurationFast(cached)
        return float(dur) if dur >= 0.0 else None

    @property
    def duration_fast(self) -> Optional[float]:
        return self.get_duration_fast()

    @property
    def time_range_fast(self) -> Optional[Tuple[int, int]]:
        return self.get_time_range_fast()

    def get_duration_fast_str(self, cached: bool = True) -> Optional[str]:
        dur_str = str(self._cpp.GetDurationFastStr(cached))
        return dur_str if dur_str and dur_str != "N/A" else None

    def get_lumi(
        self,
        start_ts: Optional[Union[int, float]] = None,
        end_ts: Optional[Union[int, float]] = None,
        lumi_dir: str = "/eos/experiment/sndlhc/atlas_lumi",
        cached: bool = True,
    ) -> float:
        s_ts = int(start_ts) if start_ts is not None else -1
        e_ts = int(end_ts) if end_ts is not None else -1
        return float(self._cpp.GetLumi(s_ts, e_ts, lumi_dir, cached))

    @property
    def lumi(self) -> float:
        return self.get_lumi()

    def get_lumi_fast(
        self,
        lumi_dir: str = "/eos/experiment/sndlhc/atlas_lumi",
        cached: bool = True,
    ) -> float:
        return float(self._cpp.GetLumiFast(lumi_dir, cached))

    @property
    def lumi_fast(self) -> float:
        return self.get_lumi_fast()

    def get_lumi_exact(
        self,
        lumi_dir: str = "/eos/experiment/sndlhc/atlas_lumi",
        cached: bool = True,
    ) -> float:
        return float(self._cpp.GetLumiExact(lumi_dir, cached))

    @property
    def lumi_exact(self) -> float:
        return self.get_lumi_exact()

    def get_lumi_str(
        self,
        start_ts: Optional[Union[int, float]] = None,
        end_ts: Optional[Union[int, float]] = None,
        lumi_dir: str = "/eos/experiment/sndlhc/atlas_lumi",
        cached: bool = True,
    ) -> str:
        s_ts = int(start_ts) if start_ts is not None else -1
        e_ts = int(end_ts) if end_ts is not None else -1
        return str(self._cpp.GetLumiStr(s_ts, e_ts, lumi_dir, cached))

    def get_lumi_fast_str(
        self,
        lumi_dir: str = "/eos/experiment/sndlhc/atlas_lumi",
        cached: bool = True,
    ) -> str:
        return str(self._cpp.GetLumiFastStr(lumi_dir, cached))

    def summary(self) -> str:
        return str(self._cpp.Summary())

    def print(self) -> None:
        self._cpp.Print()

    def __repr__(self) -> str:
        mc_str = "True" if self.isMC() else "False"
        run_part = f", run={self.run_number}" if self.run_number else ""
        fill_part = f", fill={self.fill_number}" if self.fill_number else ""
        dur_str = self.get_duration_fast_str()
        dur_part = f", duration='{dur_str}'" if dur_str else ""
        geo_part = ", geo=OK" if self.has_geometry else ""
        return f"DataManager(tree='{self.tree_name}'{run_part}{fill_part}, is_mc={mc_str}, files={self.num_files}, entries={self.entries:,}{dur_part}{geo_part})"

    @classmethod
    def load_libraries(cls, repo_root: Optional[str] = None):
        load_analysis_libraries(repo_root=repo_root)

    @classmethod
    def from_run(
        cls,
        run: int,
        n_files: int = -1,
        csv_data_path: Optional[str] = None,
        tree_name: Optional[str] = None,
        num_threads: Optional[int] = None,
        init_geo: bool = False,
        geo_path: Optional[str] = None,
        csv_geo_path: Optional[str] = None,
    ) -> "DataManager":
        return cls(
            run=run,
            n_files=n_files,
            csv_data_path=csv_data_path,
            tree_name=tree_name,
            num_threads=num_threads,
            init_geo=init_geo,
            geo_path=geo_path,
            csv_geo_path=csv_geo_path,
        )

    @staticmethod
    def get_data_base_path(run: int, csv_file_path: Optional[str] = None) -> str:
        load_analysis_libraries()
        if csv_file_path is None:
            repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            default_csv = os.path.join(repo_root, "config", "data_paths.csv")
            csv_file_path = default_csv if os.path.exists(default_csv) else ""
        return str(ROOT.snd.DataManager.FetchDataBasePath(int(run), csv_file_path or ""))

    @staticmethod
    def get_geo_path_for_run(run: int, csv_file_path: Optional[str] = None) -> str:
        load_analysis_libraries()
        if csv_file_path is None:
            repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            default_csv = os.path.join(repo_root, "config", "geo_paths.csv")
            csv_file_path = default_csv if os.path.exists(default_csv) else ""
        return str(ROOT.snd.DataManager.FetchGeoPath(int(run), csv_file_path or ""))

    @staticmethod
    def fetch_tchain(
        run_or_file: Union[int, str],
        n_files: int = -1,
        csv_file_path: Optional[str] = None,
    ) -> ROOT.TChain:
        load_analysis_libraries()
        if isinstance(run_or_file, int):
            return ROOT.snd.DataManager.FetchTChain(run_or_file, n_files, csv_file_path or "")
        return ROOT.snd.DataManager.FetchTChain(str(run_or_file))

    @staticmethod
    def fetch_geometry(
        geo_path_or_run: Union[int, str],
        csv_file_path: Optional[str] = None,
    ) -> Tuple[Any, Any]:
        load_analysis_libraries()
        if csv_file_path is None:
            repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            default_csv = os.path.join(repo_root, "config", "geo_paths.csv")
            csv_file_path = default_csv if os.path.exists(default_csv) else ""
        if isinstance(geo_path_or_run, int):
            geom = ROOT.snd.DataManager.FetchGeometry(geo_path_or_run, csv_file_path or "")
        else:
            geom = ROOT.snd.DataManager.FetchGeometry(str(geo_path_or_run))
        return (geom.first, geom.second)

    @staticmethod
    def copy_metadata(source_file: str, target_file: str, exclude_trees: Optional[List[str]] = None) -> None:
        if exclude_trees is None:
            exclude_trees = ["cbmsim", "rawConv"]
        vec = ROOT.std.vector('string')()
        for e in exclude_trees:
            vec.push_back(str(e))
        ROOT.snd.DataManager.CopyMetadata(source_file, target_file, vec)

    @staticmethod
    def fetch_lumi(
        fill: int,
        start_ts: Optional[Union[int, float]] = None,
        end_ts: Optional[Union[int, float]] = None,
        lumi_dir: str = "/eos/experiment/sndlhc/atlas_lumi",
    ) -> float:
        load_analysis_libraries()
        s_ts = int(start_ts) if start_ts is not None else -1
        e_ts = int(end_ts) if end_ts is not None else -1
        return float(ROOT.snd.DataManager.FetchLumi(int(fill), s_ts, e_ts, lumi_dir))
