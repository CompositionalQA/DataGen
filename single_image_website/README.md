# Single Image Annotation Website

A Flask-based web application for annotating individual images with Q&A pairs.

## Features

- **Single Image Annotation**: Annotate one image at a time (first image from image pairs)
- **Q&A Format**: Add questions and answers for each image
- **Approval System**: Automatically approve images when Q&A is submitted
- **Reject/Report**: Mark images as rejected or report problematic ones
- **Progress Tracking**: Visual progress bar showing annotation completion
- **Carousel**: Review previously annotated images
- **Completion Screen**: Shows when all images are annotated
- **Export**: Export all annotations as JSON

## Installation

1. Install Python dependencies:
```bash
pip install flask
```

2. Ensure you have the source data file:
   - The app loads images from `../annotation_website/pairs_no_duplicates_2.jsonl`
   - It extracts the first image (image_a) from each pair

## Running the Application

```bash
python app.py
```

The application will:
- Initialize the database
- Load images from the JSONL file
- Start the server on http://0.0.0.0:5000

## Usage

1. Open your browser to http://localhost:5000
2. Review the displayed image
3. Either:
   - Add a Q&A pair and submit (auto-approves)
   - Click "Reject Image" to mark as rejected
   - Click "Report Issues" if the image has problems
4. The system automatically loads the next unannotated image
5. Click on carousel items to review/edit previous annotations
6. Export all annotations using the "Export All" button

## Database Schema

### images table
- `id`: Unique identifier
- `source`: Dataset source
- `image_path`: Image URL/path
- `image_url`: Original image URL
- `original_meta`: Metadata from source (JSON)
- `created_at`: Timestamp

### annotations table
- `id`: Auto-increment primary key
- `image_id`: Foreign key to images
- `question`: Annotation question
- `answer`: Annotation answer
- `is_approved`: Boolean approval status
- `is_reported`: Boolean report flag
- `annotated_at`: Timestamp

## API Endpoints

- `GET /` - Main interface
- `GET /api/random_image` - Get next unannotated image
- `GET /api/image/<image_id>` - Get specific image
- `POST /api/annotate` - Save annotation
- `POST /api/report` - Report image issues
- `GET /api/stats` - Get statistics
- `GET /api/annotated_images` - Get carousel data
- `GET /api/export/all` - Export all as JSON
