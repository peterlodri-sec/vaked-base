cmake_minimum_required(VERSION 3.20.0)
project(vaked-mlir LANGUAGES CXX C)

set(CMAKE_CXX_STANDARD 17)

# Find MLIR
find_package(MLIR REQUIRED CONFIG)

# Include MLIR CMake utilities
list(APPEND CMAKE_MODULE_PATH ${MLIR_CMAKE_DIR})
include(AddMLIR)
include(HandleLLVMOptions)

# Vaked MLIR include directories
set(VAKED_INCLUDE_DIR ${CMAKE_CURRENT_SOURCE_DIR}/include)

# Add LLVM and MLIR include directories
include_directories(${LLVM_INCLUDE_DIRS})
include_directories(${MLIR_INCLUDE_DIRS})
include_directories(${VAKED_INCLUDE_DIR})

# Vaked dialect library target
add_mlir_dialect_library(VakedDialect
  lib/VakedDialect.cpp
  lib/VakedOps.cpp
  lib/VakedTypes.cpp
  lib/Pass1TopologyAnalysis.cpp

  DEPENDS
  VakedOpsIncGen
  VakedTypesIncGen
  VakedDialectIncGen
  VakedPassesIncGen
)

target_include_directories(VakedDialect
  PUBLIC
  $<BUILD_INTERFACE:${VAKED_INCLUDE_DIR}>
)

# TableGen target for Vaked operations
add_mlir_tablegen(VakedOpsIncGen
  VakedOps.td
  -gen-op-defs -gen-op-decls
  SOURCE ${CMAKE_CURRENT_SOURCE_DIR}/include/vaked/VakedOps.td
  TARGET VakedOpsIncGen
)

# TableGen target for Vaked types
add_mlir_tablegen(VakedTypesIncGen
  VakedTypes.td
  -gen-typedef-defs -gen-typedef-decls
  SOURCE ${CMAKE_CURRENT_SOURCE_DIR}/include/vaked/VakedTypes.td
  TARGET VakedTypesIncGen
)

# TableGen target for Vaked dialect
add_mlir_tablegen(VakedDialectIncGen
  VakedDialect.td
  -gen-dialect-defs -gen-dialect-decls
  SOURCE ${CMAKE_CURRENT_SOURCE_DIR}/include/vaked/VakedDialect.td
  TARGET VakedDialectIncGen
)

# TableGen target for Vaked passes
add_mlir_tablegen(VakedPassesIncGen
  VakedPasses.td
  -gen-pass-defs
  SOURCE ${CMAKE_CURRENT_SOURCE_DIR}/include/vaked/VakedPasses.td
  TARGET VakedPassesIncGen
)

# Link against MLIR libraries
target_link_libraries(VakedDialect
  PUBLIC
  MLIRIR
  MLIRInferTypeOpInterface
  MLIRSideEffectInterfaces
  MLIRPass
)

# Optional: add tests if present
if(EXISTS ${CMAKE_CURRENT_SOURCE_DIR}/test)
  add_subdirectory(test)
endif()

# Optional: add tools if present
if(EXISTS ${CMAKE_CURRENT_SOURCE_DIR}/tools)
  add_subdirectory(tools)
endif()
