cmake_minimum_required(VERSION 3.16)
project(mmm CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

if(NOT CMAKE_BUILD_TYPE)
    set(CMAKE_BUILD_TYPE Release CACHE STRING "Build type" FORCE)
endif()

# params.h (matrix + flag hash) is produced by gen.py and checked in next to it.
add_executable(mmm main.cpp sha256.h params.h)
target_include_directories(mmm PRIVATE ${CMAKE_CURRENT_SOURCE_DIR})
# Symbols are kept on purpose so check/hash_check show up in a disassembler.
target_compile_options(mmm PRIVATE -Wall -Wextra)
