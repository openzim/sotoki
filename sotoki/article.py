from libzim import ZimArticle, ZimBlob

class ContentArticle(ZimArticle):

    def __init__(self, url, title, content):
        ZimArticle.__init__(self)
        self.url = url
        self.title = title
        self.content = content

    def is_redirect(self):
        return False

    def get_url(self):
        return f"A/{self.url}"

    def get_title(self):
        return self.title
    
    def get_mime_type(self):
        return "text/html"
    
    def get_filename(self):
        return ""
    
    def should_compress(self):
        return True

    def should_index(self):
        return False

    def get_data(self):
        return ZimBlob(self.content)

class RedirectArticle(ZimArticle):

    def __init__(self, url, redirect_url, title):
        ZimArticle.__init__(self)

        self.url = url
        self.redirect_url = redirect_url
        self.title = title

    def is_redirect(self):
        return True

    def get_url(self):
        return self.url

    def get_redirect_url(self):
        return self.redirect_url

    def get_title(self):
        return self.title
    
    def get_mime_type(self):
        return "text/html"
    
    def get_filename(self):
        return ""
    
    def should_compress(self):
        return True

    def should_index(self):
        return False

    def get_data(self):
        return ZimBlob(b'')