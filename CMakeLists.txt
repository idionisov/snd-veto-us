cmake_minimum_required(VERSION 3.10)
project(sndVetoUSAnalysis CXX)

if(POLICY CMP0074)
  cmake_policy(SET CMP0074 NEW)
endif()

include(GNUInstallDirs)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# Set global output directories for libraries and executables
set(CMAKE_LIBRARY_OUTPUT_DIRECTORY ${CMAKE_BINARY_DIR}/lib)
set(CMAKE_RUNTIME_OUTPUT_DIRECTORY ${CMAKE_BINARY_DIR}/bin)

include_directories(BEFORE ${CMAKE_CURRENT_SOURCE_DIR})

# Ensure ROOT prefix directory is in CMAKE_PREFIX_PATH for internal dependency searches
if(DEFINED ENV{ROOT_ROOT})
  list(APPEND CMAKE_PREFIX_PATH $ENV{ROOT_ROOT})
endif()
if(DEFINED ENV{ROOTSYS})
  list(APPEND CMAKE_PREFIX_PATH $ENV{ROOTSYS})
endif()

# Find ROOT
find_package(ROOT REQUIRED COMPONENTS Core Tree Hist RIO)
include(${ROOT_USE_FILE})

# Check that SNDSW_ROOT is set
if(NOT DEFINED ENV{SNDSW_ROOT})
  message(FATAL_ERROR "SNDSW_ROOT environment variable is not set!")
endif()
set(SNDSW_ROOT $ENV{SNDSW_ROOT})

# Setup include directories
include_directories(
  ${CMAKE_SOURCE_DIR}/analysis
  ${SNDSW_ROOT}/include
  ${ROOT_INCLUDE_DIRS}
)

# Auto-detect FairRoot include directory
if(DEFINED ENV{FAIRROOT_ROOT})
  set(FAIRROOT_PATH $ENV{FAIRROOT_ROOT})
elseif(DEFINED ENV{FAIRROOTPATH})
  set(FAIRROOT_PATH $ENV{FAIRROOTPATH})
endif()
if(FAIRROOT_PATH)
  include_directories(${FAIRROOT_PATH}/include)
  message(STATUS "Found FairRoot include: ${FAIRROOT_PATH}/include")
else()
  message(WARNING "FairRoot include directory not found!")
endif()

# Auto-detect FairLogger include directory
if(DEFINED ENV{FAIRLOGGER_ROOT})
  set(FAIRLOGGER_PATH $ENV{FAIRLOGGER_ROOT})
endif()
if(FAIRLOGGER_PATH)
  include_directories(${FAIRLOGGER_PATH}/include)
  message(STATUS "Found FairLogger include: ${FAIRLOGGER_PATH}/include")
else()
  message(WARNING "FairLogger include directory not found!")
endif()

# Auto-detect fmt include directory
if(DEFINED ENV{FMT_ROOT})
  set(FMT_PATH $ENV{FMT_ROOT})
endif()
if(FAIRLOGGER_PATH AND NOT FMT_PATH)
  # Look near FairLogger or in cvmfs
  get_filename_component(CV_SW ${FAIRLOGGER_PATH} DIRECTORY)
  file(GLOB FMT_DIRS "${CV_SW}/fmt/*")
  if(FMT_DIRS)
    list(GET FMT_DIRS 0 FMT_PATH)
  endif()
endif()
if(FMT_PATH)
  include_directories(${FMT_PATH}/include)
  message(STATUS "Found fmt include: ${FMT_PATH}/include")
endif()

# Auto-detect VMC include directory
if(DEFINED ENV{VMC_ROOT})
  set(VMC_PATH $ENV{VMC_ROOT})
endif()
if(VMC_PATH)
  include_directories(${VMC_PATH}/include/vmc)
  message(STATUS "Found VMC include: ${VMC_PATH}/include/vmc")
endif()

# Link directories
link_directories(
  ${SNDSW_ROOT}/lib
  ${ROOT_LIBRARY_DIRS}
)

add_subdirectory(analysis)
