/*
 * replace an <img/> node with a jdidenticon <svg />
 * Uses it's parent .innerHTML so img should be wrapped.
 * @param img: either an HTMLImageElement or an Error event
 */
function replaceWithJdenticon(img) {
    if (!(img instanceof HTMLImageElement)) {
        img = img.srcElement;
    }
    if (img.getAttribute('data-jdenticon-value')) {
        img.parentNode.innerHTML = jdenticon.toSvg(img.getAttribute('data-jdenticon-value'), img.width || img.getAttribute("data-jdenticon-width"));
    }
}
var to_root = document.querySelector("meta[name=to_root]").getAttribute("content");
var webp_handler = new WebPHandler({
    on_error: replaceWithJdenticon,
    scripts_urls: [to_root + "static/js/webp-hero.polyfill.js", to_root + "static/js/webp-hero.bundle.js"],
});

document.addEventListener('DOMContentLoaded', function(){
    var img_elements = document.querySelectorAll('img');
    for (var i=0; i<img_elements.length; i++) {
        replaceWithJdenticon(img_elements[i])
    }
});
