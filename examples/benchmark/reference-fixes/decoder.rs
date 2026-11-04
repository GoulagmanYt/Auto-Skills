pub fn decode_frame(bytes: &[u8]) -> Result<&[u8], &'static str> {
    let header = bytes.get(..2).ok_or("short header")?;
    let length = u16::from_be_bytes([header[0], header[1]]) as usize;
    bytes.get(2..2 + length).ok_or("truncated payload")
}
