unsafe extern "C" {
    fn verify_flag(bytes: *const u8, length: usize) -> i32;
}

pub fn verify(input: &str) -> bool {
    unsafe { verify_flag(input.as_ptr(), input.len()) != 0 }
}
