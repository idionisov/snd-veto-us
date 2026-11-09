include_directories(BEFORE ${CMAKE_CURRENT_SOURCE_DIR})

# Header files for dictionary generation
set(ANALYSIS_HEADERS
  DataManager.h
)

set(ANALYSIS_SRCS
  DataManager.cxx
)

# ROOT generate dictionary
root_generate_dictionary(G__snd_analysis
  ${ANALYSIS_HEADERS}
  LINKDEF AnalysisLinkDef.h
)

# Add library for analysis
add_library(snd_analysis SHARED
  ${ANALYSIS_SRCS}
  G__snd_analysis.cxx
)

# Find sndsw dependencies
find_library(SHIP_DATA_LIB ShipData PATHS "${SNDSW_ROOT}/lib" NO_DEFAULT_PATH REQUIRED)
find_library(SHIP_LHC_LIB shipLHC PATHS "${SNDSW_ROOT}/lib" NO_DEFAULT_PATH REQUIRED)
find_library(ANALYSIS_TOOLS_LIB snd_analysis_tools PATHS "${SNDSW_ROOT}/lib" NO_DEFAULT_PATH REQUIRED)

target_link_libraries(snd_analysis
  PUBLIC
    ROOT::Core
    ROOT::Tree
    ROOT::ROOTDataFrame
    ROOT::RIO
    ROOT::Hist
    ROOT::Geom
    ${SHIP_DATA_LIB}
    ${SHIP_LHC_LIB}
    ${ANALYSIS_TOOLS_LIB}
)
