#import "Basic";
#import "Compiler";
#import "File";

#run {
    set_build_options_dc(.{do_output = false});

    options := get_build_options();

    options.stack_trace = false;
    options.output_type = .EXECUTABLE;
    options.output_executable_name = "transmitter";
    options.backtrace_on_crash = .OFF;
    options.additional_linker_arguments = string.["--no-export-dynamic", "--strip-all"];
    set_optimization(*options, .OPTIMIZED, preserve_debug_info=false);

    workspace := compiler_create_workspace("transmitter");
    set_build_options(options, workspace);
    add_build_file("transmitter.jai", workspace);
}
