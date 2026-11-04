pub fn decode_frame(bytes: &[u8]) -> Result<&[u8], &'static str> {
    let length = u16::from_be_bytes([bytes[0], bytes[1]]) as usize;
    Ok(&bytes[2..2 + length])
}
