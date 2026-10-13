from datetime import datetime, timezone

from bff.epg import parse_now_next, parse_xmltv_time

XMLTV = b"""<?xml version="1.0" encoding="UTF-8"?>
<tv>
  <programme start="20240101120000 +0000" stop="20240101130000 +0000" channel="bbc1.uk">
    <title>News at Noon</title>
    <desc>The latest news.</desc>
  </programme>
  <programme start="20240101130000 +0000" stop="20240101140000 +0000" channel="bbc1.uk">
    <title>Afternoon Show</title>
  </programme>
  <programme start="20240101123000 +0000" stop="20240101133000 +0000" channel="itv.uk">
    <title>ITV Now</title>
  </programme>
  <programme start="20240101150000 +0000" channel="bbc1.uk">
    <title>No Stop</title>
  </programme>
</tv>
"""

NOW = datetime(2024, 1, 1, 12, 30, tzinfo=timezone.utc)


def test_parse_xmltv_time_with_offset_and_without():
    assert parse_xmltv_time("20240101120000 +0000") == datetime(
        2024, 1, 1, 12, 0, tzinfo=timezone.utc
    )
    assert parse_xmltv_time("20240101120000") == datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc)
    assert parse_xmltv_time("garbage") is None
    assert parse_xmltv_time(None) is None


def test_now_next_are_extracted_per_channel():
    result = parse_now_next(XMLTV, NOW)

    bbc = result["bbc1.uk"]
    assert bbc["now"]["title"] == "News at Noon"
    assert bbc["now"]["description"] == "The latest news."
    # The earliest programme starting after 12:30 is the 13:00 show.
    assert bbc["next"]["title"] == "Afternoon Show"

    itv = result["itv.uk"]
    assert itv["now"]["title"] == "ITV Now"
    assert itv["next"] is None


def test_a_null_stop_programme_never_expires_and_can_be_next():
    # At 14:30 the 13:00-14:00 show has ended; the unbounded 15:00 show is next.
    result = parse_now_next(XMLTV, datetime(2024, 1, 1, 14, 30, tzinfo=timezone.utc))
    bbc = result["bbc1.uk"]
    assert bbc["now"] is None
    assert bbc["next"]["title"] == "No Stop"
    assert bbc["next"]["stop"] is None


def test_earliest_next_wins():
    xml = b"""<?xml version="1.0"?><tv>
      <programme start="20240101130000 +0000" channel="x"><title>Later</title></programme>
      <programme start="20240101123000 +0000" channel="x"><title>Sooner</title></programme>
    </tv>"""
    result = parse_now_next(xml, datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc))
    assert result["x"]["next"]["title"] == "Sooner"
