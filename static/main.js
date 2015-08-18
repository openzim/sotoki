$('span.date').each(function(index, elt) {
    var element = $(elt);
    element.html(moment(element.html()).fromNow());
});
 
