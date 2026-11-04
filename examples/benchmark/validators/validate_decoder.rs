#[path = "__SOURCE__"]
mod decoder;

#[test]
fn decoder_handles_short_header_and_payload_without_panicking() {
    assert_eq!(decoder::decode_frame(&[]), Err("short header"));
    assert_eq!(decoder::decode_frame(&[0]), Err("short header"));
    assert_eq!(decoder::decode_frame(&[0, 3, 10, 11]), Err("truncated payload"));
    assert_eq!(decoder::decode_frame(&[255, 255, 1]), Err("truncated payload"));
    for length in 0..=255_u16 {
        let header = length.to_be_bytes();
        let frame = [header[0], header[1], 42];
        let result = std::panic::catch_unwind(|| decoder::decode_frame(&frame));
        assert!(result.is_ok(), "decoder panicked for length {}", length);
    }
}

#[test]
fn decoder_preserves_complete_payload_borrow_and_accepts_trailing_bytes() {
    assert_eq!(decoder::decode_frame(&[0, 0]), Ok(&[][..]));
    let frame = [0, 3, 42, 0, 255, 99];
    let payload = decoder::decode_frame(&frame).unwrap();
    assert_eq!(payload, &[42, 0, 255]);
    assert_eq!(payload.as_ptr(), frame[2..].as_ptr());
}
