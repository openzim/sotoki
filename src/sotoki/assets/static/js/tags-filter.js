var to_root = document.querySelector("meta[name=to_root]").getAttribute("content");

// helper for enabling IE 8 event bindings
function addEvent(el, type, handler) {
    if (el.attachEvent) el.attachEvent('on'+type, handler); else el.addEventListener(type, handler);
}

// live binding helper
function live(selector, event, callback, context) {
    addEvent(context || document, event, function(e) {
        var found, el = e.target || e.srcElement;
        while (el && !(found = el.id == selector)) el = el.parentElement;
        if (found) callback.call(el, e);
    });
}

function createTagCard(tagName, nbQuestions) {
    let elem = document.createElement("div");
    elem.className = 's-card js-tag-cell grid fd-column suggested';
    elem.innerHTML = '<div class="grid jc-space-between ai-center mb12"><div class="grid--cell"><a href="' + to_root + 'questions/tagged/__TAG__" class="post-tag" title="show questions tagged \'__TAG__\'" rel="tag">__TAG__</a></div></div><div class="mt-auto grid jc-space-between fs-caption fc-black-400"><div class="grid--cell">__NB_QUESTIONS__ question__QUESTIONS_PLURAL__</div></div>'.replaceAll('__TAG__', tagName).replaceAll('__NB_QUESTIONS__', nbQuestions).replaceAll('__QUESTIONS_PLURAL__', (nbQuestions == 1) ? '' : 's');
    return elem;
}
var tagfilterEle = document.getElementById("tagfilter");
var tagsBrowserEle = document.getElementById("tags-browser");
document.addEventListener('DOMContentLoaded', function() {
    window.tags = [];
    console.log('Registering tag filter');
    fetch("api/tags.json")
        .then(response => {
            return response.json();
        }).then(function (data){
            window.tags = data;
            live(tagfilterEle.id, 'input', function() {
                let search = tagfilterEle.value.toLowerCase().trim();
                let matchingTags = [];
                console.log('input changed to', search);

                // hide static items unless we have no search
                if (search.length) {
                    console.log("search, hiding originals");
                    document.querySelectorAll("div.original").forEach(function (elem) {
                        if (elem.className.indexOf('d-none') == -1)
                            elem.className += ' d-none';
                    });
                } else {
                    console.log("search cleared, restoring originals");
                    document.querySelectorAll("div.original").forEach(function (elem) {
                        elem.className = elem.className.replace(' d-none', '');
                    });
                }

                if (search.length) {
                    matchingTags = window.tags.filter(function (item) {
                        return (~item[0].indexOf(search));
                    }).slice(0, 36); // max 36 elems
                }

                // first remove previous results
                console.log("removing suggesteds");
                document.querySelectorAll("div.suggested").forEach(function (elem) {
                    elem.parentNode.removeChild(elem);
                });

                if (matchingTags.length) {
                    console.log("matches, appending results", matchingTags.length);
                    matchingTags.forEach(function (item) {
                        tagsBrowserEle.appendChild(createTagCard(item[0], item[1]));
                    });
                }
            });
        });
});
