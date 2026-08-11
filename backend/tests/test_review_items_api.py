import uuid

from app.models.review import ReviewItem


def test_list_review_items_empty(client):
    response = client.get("/api/v1/review-items")
    assert response.status_code == 200
    data = response.json()
    assert data["items"] == []
    assert data["total"] == 0
    assert data["limit"] == 50
    assert data["offset"] == 0


def test_list_review_items_filtering(client, db_session):
    item1 = ReviewItem(
        id=uuid.uuid4(),
        review_type="bookkeeping",
        status="pending",
        priority="high",
        source_type="document",
        source_id=uuid.uuid4(),
        title="Review Item Pending",
        summary="Low confidence score",
    )
    item2 = ReviewItem(
        id=uuid.uuid4(),
        review_type="extraction",
        status="approved",
        priority="normal",
        source_type="document",
        source_id=uuid.uuid4(),
        title="Review Item Approved",
        summary="Approved by human",
    )
    db_session.add_all([item1, item2])
    db_session.commit()

    # Filter status=pending
    response = client.get("/api/v1/review-items?status=pending")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert len(data["items"]) == 1
    assert data["items"][0]["title"] == "Review Item Pending"

    # Filter review_type=extraction
    response = client.get("/api/v1/review-items?review_type=extraction")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["items"][0]["title"] == "Review Item Approved"


def test_get_review_item_detail_success(client, db_session):
    item_id = uuid.uuid4()
    source_id = uuid.uuid4()
    item = ReviewItem(
        id=item_id,
        review_type="bookkeeping",
        status="pending",
        priority="high",
        source_type="document",
        source_id=source_id,
        title="Review Bank Account",
        summary="Bank account used",
        suggested_action="Review lines",
        original_payload={"vendor_name": "Gramedia", "total": 150000},
    )
    db_session.add(item)
    db_session.commit()

    response = client.get(f"/api/v1/review-items/{item_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == str(item_id)
    assert data["title"] == "Review Bank Account"
    assert data["original_payload"]["vendor_name"] == "Gramedia"


def test_get_review_item_detail_not_found(client):
    random_uuid = uuid.uuid4()
    response = client.get(f"/api/v1/review-items/{random_uuid}")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"]


def test_get_review_item_detail_invalid_uuid(client):
    response = client.get("/api/v1/review-items/invalid-uuid-string")
    assert response.status_code == 400
    assert "Invalid review item UUID format" in response.json()["detail"]
