class Parsed_song:
    def __init__(self, id=None, name=None, artists=None, album_id=None, duration_ms=None, external_urls=None, uri=None):
        self.id = id
        self.name = name
        self.artists = artists
        self.album_id = album_id
        self.duration_ms = duration_ms
        self.external_urls = external_urls
        self.uri = uri
    
    def __repr__(self):
        return f"Parsed_song(id={self.id}, name={self.name}, artists={self.artists}, album_id={self.album_id}, duration_ms={self.duration_ms}, external_urls={self.external_urls}, uri={self.uri})"