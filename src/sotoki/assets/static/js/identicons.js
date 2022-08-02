/*
 * replace an <img/> node with a jdidenticon <svg />
 * Uses it's parent .innerHTML so img should be wrapped.
 * @param img: either an HTMLImageElement or an Error event
 */
function replaceWithJdenticon(img) {
    if (!(img instanceof HTMLImageElement)) {
        img = img.srcElement;
    }
    if (img.getAttribute('data-jdenticon-value') || img.getAttribute('data-jdenticon-hash')) {
        img.parentNode.innerHTML = jdenticon.toSvg(img.getAttribute('data-jdenticon-value') || img.getAttribute('data-jdenticon-hash'), img.width || img.getAttribute("data-jdenticon-width"));
    }
}
var to_root = document.querySelector("meta[name=to_root]").getAttribute("content");
var webp_handler = new WebPHandler({
    on_error: replaceWithJdenticon,
    scripts_urls: [to_root + "static/js/webp-hero.polyfill.js", to_root + "static/js/webp-hero.bundle.js"],
});

/*
 * manually set (in-templates) on all <img /> nodes so that any error loading
 * it by the browser calls it. Used to trigger polyfill and jdenticon fallback
 * /!\ requires WebPHandler to be ready _before_ the browser attempts to 
 * load any image in the page. WebP Hero scripts should thus be included
 * syncrhonously before this */
function onImageLoadingError(img) {
    if (img === undefined)
        return;

    // only use polyfill if browser lacks Webp supports and wasn't already polyfied
    // polyfill replaces url with data URI
    if (!webp_handler.supports_webp && img.src.length > 0 && img.src.substr(0, 5) != "data:") {
        webp_handler.polyfillImage(img);
        return;
    }

    // defaults to rendering as Jdenticon
    replaceWithJdenticon(img);
}

document.addEventListener('DOMContentLoaded', function(){
    var img_elements = document.querySelectorAll('img');
    for (var i=0; i<img_elements.length; i++) {
        img_elements[i].addEventListener('error', onImageLoadingError);
    }
});
