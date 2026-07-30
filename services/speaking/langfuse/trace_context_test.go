package langfuse

import "testing"

func TestParseTraceparent(t *testing.T) {
	traceID := "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
	parentID := "bbbbbbbbbbbbbbbb"

	gotTraceID, gotParentID, ok := ParseTraceparent(
		"00-" + traceID + "-" + parentID + "-01",
	)
	if !ok {
		t.Fatal("expected valid traceparent")
	}
	if gotTraceID != traceID || gotParentID != parentID {
		t.Fatalf(
			"expected trace %q parent %q, got trace %q parent %q",
			traceID,
			parentID,
			gotTraceID,
			gotParentID,
		)
	}
}

func TestParseTraceparentRejectsAbsentMalformedAndZeroIDs(t *testing.T) {
	values := []string{
		"",
		"malformed",
		"00-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa-short-01",
		"00-00000000000000000000000000000000-bbbbbbbbbbbbbbbb-01",
		"00-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa-0000000000000000-01",
	}

	for _, value := range values {
		if _, _, ok := ParseTraceparent(value); ok {
			t.Fatalf("expected %q to be rejected", value)
		}
	}
}
