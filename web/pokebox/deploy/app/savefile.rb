require_relative "charmap"

# Minimal Generation III (Emerald) save parser.
#
# A .sav is 128 KiB: two game save blocks (A and B) of 14 sections each.
# Each section is 4 KiB with a footer holding: section id, checksum, save index.
# The block with the higher save index is the current one.
#
# We only read what the box viewer displays:
#   - the trainer name            (section 0, SaveBlock2, offset 0x00)
#   - the party: count + each mon's species id and nickname
#
# Nicknames are stored UNENCRYPTED at offset 0x08 of each 100-byte party mon,
# so we never need to touch the PID-keyed substructure encryption.
module SaveFile
  SECTION_SIZE   = 0x1000
  SECTIONS       = 14
  BLOCK_SIZE     = SECTION_SIZE * SECTIONS      # 0xE000
  SAVE_SIZE      = 0x20000                       # 128 KiB

  # Footer layout inside each 4 KiB section (last 128 bytes are footer area).
  FOOTER_ID       = 0x0FF4   # u16 section id
  FOOTER_CHECKSUM = 0x0FF6   # u16 checksum
  FOOTER_SAVEIDX  = 0x0FFC   # u32 save index

  # How many bytes of each section are covered by the checksum (per section id).
  # Section 0 covers 3884 bytes; most others 3968. Values from the Gen-3 spec.
  CHECKSUM_BYTES = {
    0 => 3884, 1 => 3968, 2 => 3968, 3 => 3968, 4 => 3848,
    5 => 3968, 6 => 3968, 7 => 3968, 8 => 3968, 9 => 3968,
    10 => 3968, 11 => 3968, 12 => 3968, 13 => 2000
  }.freeze

  # --- SaveBlock2 (section 0) fields ---
  TRAINER_NAME_OFF = 0x0000
  TRAINER_NAME_LEN = 7
  GENDER_OFF       = 0x0008   # u8: 0 = boy, 1 = girl
  TRAINER_ID_OFF   = 0x000A   # u32; low u16 is the visible ID
  PLAYTIME_H_OFF   = 0x000E   # u16 hours
  PLAYTIME_M_OFF   = 0x0010   # u8 minutes
  PLAYTIME_S_OFF   = 0x0011   # u8 seconds

  # --- SaveBlock1 (sections 1..4) fields ---
  PARTY_COUNT_OFF  = 0x0234
  PARTY_ARRAY_OFF  = 0x0238
  MON_SIZE         = 100
  MON_NICK_OFF     = 0x08
  MON_NICK_LEN     = 10
  MON_LEVEL_OFF    = 84       # unencrypted, in the Pokemon wrapper
  MON_HP_OFF       = 86
  MON_MAXHP_OFF    = 88
  MAX_PARTY        = 6

  class ParseError < StandardError; end

  Mon   = Struct.new(:nickname, :level, :hp, :max_hp)
  Save  = Struct.new(:trainer_name, :trainer_id, :gender, :play_h, :play_m, :play_s, :party)

  def self.gen3_checksum(bytes)
    acc = 0
    bytes.each_slice(4) do |b0, b1, b2, b3|
      word = (b0 || 0) | ((b1 || 0) << 8) | ((b2 || 0) << 16) | ((b3 || 0) << 24)
      acc = (acc + word) & 0xFFFFFFFF
    end
    ((acc & 0xFFFF) + (acc >> 16)) & 0xFFFF
  end

  # Read one game block (14 sections), validating each section checksum, and
  # return section_id => raw 4 KiB section bytes. Raises on a bad checksum.
  def self.read_block(data, block_index)
    base = block_index * BLOCK_SIZE
    sections = {}
    save_index = nil
    SECTIONS.times do |i|
      off = base + i * SECTION_SIZE
      sec = data[off, SECTION_SIZE].bytes
      raise ParseError, "truncated section" if sec.length < SECTION_SIZE

      sid = sec[FOOTER_ID] | (sec[FOOTER_ID + 1] << 8)
      raise ParseError, "bad section id #{sid}" if sid >= SECTIONS

      stored = sec[FOOTER_CHECKSUM] | (sec[FOOTER_CHECKSUM + 1] << 8)
      calc   = gen3_checksum(sec[0, CHECKSUM_BYTES.fetch(sid)])
      raise ParseError, "checksum mismatch in section #{sid}" if stored != calc

      idx = sec[FOOTER_SAVEIDX] | (sec[FOOTER_SAVEIDX + 1] << 8) |
            (sec[FOOTER_SAVEIDX + 2] << 16) | (sec[FOOTER_SAVEIDX + 3] << 24)
      save_index = idx if save_index.nil?

      sections[sid] = sec
    end
    [sections, save_index]
  end

  # SaveBlock1 (party, etc.) spans sections 1..4; SaveBlock2 (trainer) is section 0.
  # Reassemble SaveBlock1's logical bytes by concatenating sections 1,2,3,4.
  def self.reassemble_saveblock1(sections)
    (1..4).map { |sid| sections.fetch(sid)[0, 0xF80] }.flatten
  end

  def self.parse(data)
    raise ParseError, "wrong size" if data.bytesize < SAVE_SIZE

    # Pick the active block by higher save index.
    blocks = [0, 1].map { |b| read_block(data, b) rescue nil }.compact
    raise ParseError, "no valid save block" if blocks.empty?
    sections, = blocks.max_by { |(_s, idx)| idx }

    sb2 = sections.fetch(0)
    trainer = Charmap.decode(sb2[TRAINER_NAME_OFF, TRAINER_NAME_LEN])
    tid     = sb2[TRAINER_ID_OFF] | (sb2[TRAINER_ID_OFF + 1] << 8)
    gender  = sb2[GENDER_OFF] == 1 ? "Girl" : "Boy"
    play_h  = sb2[PLAYTIME_H_OFF] | (sb2[PLAYTIME_H_OFF + 1] << 8)
    play_m  = sb2[PLAYTIME_M_OFF]
    play_s  = sb2[PLAYTIME_S_OFF]

    sb1 = reassemble_saveblock1(sections)
    count = [sb1[PARTY_COUNT_OFF].to_i, MAX_PARTY].min
    party = []
    count.times do |i|
      base  = PARTY_ARRAY_OFF + i * MON_SIZE
      nick  = Charmap.decode(sb1[base + MON_NICK_OFF, MON_NICK_LEN])
      level = sb1[base + MON_LEVEL_OFF].to_i
      hp    = sb1[base + MON_HP_OFF].to_i   | (sb1[base + MON_HP_OFF + 1].to_i << 8)
      maxhp = sb1[base + MON_MAXHP_OFF].to_i | (sb1[base + MON_MAXHP_OFF + 1].to_i << 8)
      party << Mon.new(nick, level, hp, maxhp)
    end

    Save.new(trainer, tid, gender, play_h, play_m, play_s, party)
  end
end
