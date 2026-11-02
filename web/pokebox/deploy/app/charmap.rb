# Generation III (Western / Emerald) character encoding.
# Only the subset we need to decode trainer names and nicknames.
# Source of truth: pret/pokeemerald charmap.txt
module Charmap
  TERMINATOR = 0xFF

  TABLE = {}

  ("0".."9").each_with_index { |c, i| TABLE[0xA1 + i] = c }
  ("A".."Z").each_with_index { |c, i| TABLE[0xBB + i] = c }
  ("a".."z").each_with_index { |c, i| TABLE[0xD5 + i] = c }

  {
    0x00 => " ", 0x2D => "&", 0x2E => "+", 0x35 => "=", 0x36 => ";",
    0x5B => "%", 0x5C => "(", 0x5D => ")", 0x85 => "<", 0x86 => ">",
    0xAB => "!", 0xAC => "?", 0xAD => ".", 0xAE => "-", 0xB4 => "'",
    0xB8 => ",", 0xBA => "/", 0xF0 => ":"
  }.each { |b, c| TABLE[b] = c }

  # Decode a fixed-width field: stop at the 0xFF terminator (as the real games do).
  # Unknown bytes become nothing (dropped) so garbage padding never corrupts output.
  def self.decode(bytes)
    out = +""
    bytes.each do |b|
      break if b == TERMINATOR
      ch = TABLE[b]
      out << ch if ch
    end
    out
  end
end
