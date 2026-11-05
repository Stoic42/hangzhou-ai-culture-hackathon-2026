set(APP_PATH ${CMAKE_CURRENT_LIST_DIR})
get_filename_component(APP_NAME ${APP_PATH} NAME)

aux_source_directory(${APP_PATH}/src APP_SRCS)
aux_source_directory(${APP_PATH}/src/generated APP_GEN_SRCS)

add_library(${EXAMPLE_LIB})
target_sources(${EXAMPLE_LIB} PRIVATE ${APP_SRCS} ${APP_GEN_SRCS})
target_include_directories(${EXAMPLE_LIB} PRIVATE ${APP_PATH}/src)
target_include_directories(${EXAMPLE_LIB} PRIVATE ${APP_PATH}/src/generated)
