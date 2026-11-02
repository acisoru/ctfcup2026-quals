#load "protocol.jai";

usage :: () {
    print("Usage: transmitter FLAG OUTPUT.wav\n");
}

main :: () {
    args := get_command_line_arguments();

    if args.count == 2 && args[1] == "--help" {
        usage();
        return;
    }

    if args.count != 3 {
        usage();
        exit(2);
    }

    payload  := args[1];
    out_file := args[2];

    if payload.count < 8 || payload.count > MAX_PAYLOAD_BYTES {
        fail("Payload length must be 8..4096 bytes.");
    }

    if !write_capture(out_file, payload, random_generator()) {
        fail("Cannot write the capture.");
    }
}
