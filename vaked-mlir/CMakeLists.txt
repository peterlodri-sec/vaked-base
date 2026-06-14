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

  DEPENDS
  VakedOpsIncGen
  VakedTypesIncGen
  VakedDialectIncGen
)

# HCP dialect library target
add_mlir_dialect_library(HcpDialect
  lib/HcpDialect.cpp

  DEPENDS
  HcpOpsIncGen
  HcpTypesIncGen
  HcpDialectIncGen
)

# Vaked passes library target
add_library(VakedPasses
  lib/Pass1TopologyAnalysis.cpp
  lib/Pass2WalInjection.cpp
  lib/Pass3AotIndex.cpp
)
target_link_libraries(VakedPasses
  PUBLIC
  VakedDialect
  HcpDialect
  MLIRPass
  MLIRIR
  MLIRTransforms
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

# TableGen target for HCP operations
add_mlir_tablegen(HcpOpsIncGen
  HcpOps.td
  -gen-op-defs -gen-op-decls
  SOURCE ${CMAKE_CURRENT_SOURCE_DIR}/include/hcp/HcpOps.td
  TARGET HcpOpsIncGen
)

# TableGen target for HCP types
add_mlir_tablegen(HcpTypesIncGen
  HcpTypes.td
  -gen-typedef-defs -gen-typedef-decls
  SOURCE ${CMAKE_CURRENT_SOURCE_DIR}/include/hcp/HcpTypes.td
  TARGET HcpTypesIncGen
)

# TableGen target for HCP dialect
add_mlir_tablegen(HcpDialectIncGen
  HcpDialect.td
  -gen-dialect-defs -gen-dialect-decls
  SOURCE ${CMAKE_CURRENT_SOURCE_DIR}/include/hcp/HcpDialect.td
  TARGET HcpDialectIncGen
)

# Link against MLIR libraries
target_link_libraries(VakedDialect
  PUBLIC
  MLIRIR
  MLIRInferTypeOpInterface
  MLIRSideEffectInterfaces
  MLIRPass
)

# vaked-opt tool
add_executable(vaked-opt tools/vaked-opt.cpp)
target_link_libraries(vaked-opt
  PRIVATE
  VakedDialect
  HcpDialect
  VakedPasses
  MLIRIR
  MLIROptLib
)

# Optional: add tests if present
if(EXISTS ${CMAKE_CURRENT_SOURCE_DIR}/test)
  # Integration tests
  add_test(
    NAME vaked-e2e-test
    COMMAND vaked-opt -pass-pipeline="builtin.module(vaked-topology-analysis,vaked-to-hcp-lowering,vaked-aot-index)" ${CMAKE_CURRENT_SOURCE_DIR}/test/integration-e2e.mlir
  )
endif()

# Optional: add tools subdirectory if present
if(EXISTS ${CMAKE_CURRENT_SOURCE_DIR}/tools/CMakeLists.txt)
  add_subdirectory(tools)
endif()
